import math
from typing import Any
import salabim as sim

from src.management.base import Management, Snapshot, Decision
from src.infrastructure.edge import Edge, TransportOrder
from src.infrastructure.production_node import ProductionOrder


class WeighSafeStockManagement(Management):
    """Weigh-safe-stock management — demand-driven with safe-stock weighted priority.

    Shift schedule is read per production line from each node's
    ``shift_duration``, ``decision_offset``, ``production_start_times``
    attributes.  There are no global shift parameters.

    Decision cycle
    --------------
    1. Wake at each *decision time* for any line (handling multiple lines
       with different schedules).
    2. Issue FG demand orders (fg_storage → sink).
    3. Trace new FG demands (within next 24h) through the full BOM tree,
       accumulating which SKUs need production.
    4. Compute *shortage ratio* = total_stock / total_safe_stock for each active SKU.
    5. Sort by ratio ascending (most urgent first).
    6. For each production line at decision time, assign the most urgent SKU
       it can produce.  Quantity = line speed * line's shift_duration.
    7. Issue production orders (activate_time = line's upcoming production start).
    8. Issue transport orders for the full supply tree (toggleable via
       *transport_mode*), using per-order activate_time / expect_time.

    Parameters
    ----------
    safe_stock_config : list[dict]
        Each dict has ``{sku, safe_stock, …}`` — used to compute per-SKU
        total safe stock.
    nodes : dict[str, Component]
    edges : list[Edge]
    demand_orders : list[dict], optional
    trace_mode : str
        ``"full"`` (trace FG→WIP→raw from FG demand) or ``"split"`` (trace
        FG→WIP via FG demand, WIP→raw via WIP demand). Default ``"full"``.
    transport_mode : str
        ``"full_tree"`` (issue all transport orders alongside production) or
        ``"separate"`` (transports handled independently). Default ``"full_tree"``.
    decision_interval : float
        Minimum wake interval (used for demand issuance; decision times
        dynamically schedule exact wake-ups).
    """

    def __init__(
        self,
        safe_stock_config: list[dict],
        nodes: dict[str, Any],
        edges: list[Edge],
        demand_orders: list[dict] | None = None,
        trace_mode: str = "full",
        transport_mode: str = "full_tree",
        decision_interval: float = 10.0,
        name: str = "WeighSafeStockManagement",
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self._safe_stock_config = list(safe_stock_config)
        self._demand_orders = list(demand_orders or [])
        self._trace_mode = trace_mode
        self._transport_mode = transport_mode

        self._next_oid_counter: int = 1

        super().__init__(
            nodes=nodes, edges=edges,
            name=name, decision_interval=decision_interval, env=env, **kwargs,
        )

        # -- per-line shift info (read from ProductionNode attributes) -----
        self._per_line_info: dict[str, dict] = {}
        for name, pnode in self._production_nodes.items():
            sd = pnode.shift_duration
            do = pnode.decision_offset
            pst = pnode.production_start_times
            if sd is None or do is None or pst is None:
                raise ValueError(
                    f"Production node '{name}' is missing shift configuration "
                    f"(shift_duration={sd}, decision_offset={do}, "
                    f"production_start_times={pst}).  "
                    f"Every production node must have these fields."
                )
            self._per_line_info[name] = {
                "shift_duration": float(sd),
                "decision_offset": float(do),
                "production_start_times": sorted(float(t) for t in pst),
            }

        # -- line → SKU mapping (from BOM) ---------------------------------
        self._line_skus: dict[str, list[str]] = {}
        for name, pnode in self._production_nodes.items():
            self._line_skus[name] = list(pnode.bom.keys())

        # -- SKU → eligible lines -------------------------------------------
        self._sku_lines: dict[str, list[str]] = {}
        for line_name, skus in self._line_skus.items():
            for sku in skus:
                self._sku_lines.setdefault(sku, []).append(line_name)

        # -- line capacity per shift (speed * line's shift_duration) --------
        self._line_capacity: dict[str, dict[str, int]] = {}
        for name, pnode in self._production_nodes.items():
            cap = {}
            sd = self._per_line_info[name]["shift_duration"]
            for sku, bom_entry in pnode.bom.items():
                speed = bom_entry.get("speed", 0)
                if speed == 0:
                    sku_obj = getattr(pnode, 'sku_registry', None) or {}
                    sku_obj = sku_obj.get(sku) if isinstance(sku_obj, dict) else None
                    if sku_obj and sku_obj.bom_speed > 0:
                        speed = sku_obj.bom_speed
                    else:
                        speed = 1.0
                cap[sku] = max(1, int(speed * sd))
            self._line_capacity[name] = cap

        # -- per-SKU total safe stock (sum across all config entries) -------
        self._safe_stock_total: dict[str, int] = {}
        for entry in self._safe_stock_config:
            sku = entry["sku"]
            self._safe_stock_total[sku] = (
                self._safe_stock_total.get(sku, 0) + entry["safe_stock"]
            )

        # -- demand / tracing state -----------------------------------------
        self._next_demand_idx = 0
        self._issued_demand: set[int] = set()
        self._active_skus: set[str] = set()

        # -- round-robin counters per SKU -----------------------------------
        self._rr_counter: dict[str, int] = {}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _next_oid(self) -> int:
        self._next_oid_counter += 1
        return self._next_oid_counter

    # ------------------------------------------------------------------
    # Per-line decision-time helpers
    # ------------------------------------------------------------------

    def _line_decision_times(self, line_name: str, now: float) -> list[float]:
        """Return decision times for *line_name* within ±1 day of *now*."""
        info = self._per_line_info[line_name]
        prod_starts = info["production_start_times"]
        decision_offset = info["decision_offset"]
        base = math.floor(now / 1440) * 1440
        times: list[float] = []
        for day_off in (0, 1):
            for ps in prod_starts:
                dt = base + day_off * 1440 + ps - decision_offset
                times.append(dt)
        return times

    def _is_line_decision_time(self, line_name: str, now: float) -> bool:
        """Return True if *now* is a decision time for *line_name*."""
        for dt in self._line_decision_times(line_name, now):
            if abs(now - dt) < 1e-6:
                return True
        return False

    def _lines_at_decision_time(self, now: float) -> list[str]:
        """Return all production lines whose decision time matches *now*."""
        return [
            name for name in self._per_line_info
            if self._is_line_decision_time(name, now)
        ]

    def _line_next_decision_time(self, line_name: str, now: float) -> float:
        """Return the next decision time for *line_name* strictly after *now*."""
        return min(
            dt for dt in self._line_decision_times(line_name, now)
            if dt > now + 1e-9
        )

    def _next_decision_time(self, now: float) -> float:
        """Return the next decision time (across all lines) after *now*."""
        next_dt = float('inf')
        for line_name in self._per_line_info:
            dt = self._line_next_decision_time(line_name, now)
            if dt < next_dt:
                next_dt = dt
        return next_dt

    def _line_production_start(self, line_name: str, decision_time: float) -> float:
        """Return production start for *line_name* corresponding to *decision_time*."""
        info = self._per_line_info[line_name]
        for dt in self._line_decision_times(line_name, decision_time):
            if abs(decision_time - dt) < 1e-6:
                shift_idx = self._line_decision_times(line_name, decision_time).index(dt)
                prod_starts = info["production_start_times"]
                day_off = shift_idx // len(prod_starts)
                ps_idx = shift_idx % len(prod_starts)
                base = math.floor(decision_time / 1440) * 1440
                return base + day_off * 1440 + prod_starts[ps_idx]
        # Fallback (shouldn't happen if called at a real decision time)
        return decision_time + info["decision_offset"]

    def _is_decision_time(self, now: float) -> bool:
        """Return True if *now* is a decision time for any line."""
        return bool(self._lines_at_decision_time(now))

    # ------------------------------------------------------------------
    # SALABIM process — dynamic scheduling to exact decision times
    # ------------------------------------------------------------------

    def process(self):
        """Periodic loop — wake for demand issuance and at exact decision times.

        Uses ``_next_decision_time`` to dynamically jump to the next
        decision time across all lines, while never exceeding the regular
        *decision_interval* (for demand processing).
        """
        while True:
            now = self.env.now()

            # Always issue demand orders
            info = self.gather_info()
            demand_decision = Decision()
            self._issue_demand_orders(demand_decision, now)
            self._execute_decision(demand_decision)

            # At decision time: full decision cycle for matching lines
            lines = self._lines_at_decision_time(now)
            if lines:
                info = self.gather_info()
                decision = self._make_weigh_decision(now, info, lines)
                self._execute_decision(decision)

            # Schedule next wake-up: at next decision time or decision_interval
            next_dt = self._next_decision_time(now)
            next_wake = min(now + self.decision_interval, next_dt)
            if next_wake <= now + 1e-9:
                next_wake = now + self.decision_interval
            yield self.hold(next_wake - now)

    # ------------------------------------------------------------------
    # _make_weigh_decision — full decision cycle for specified lines
    # ------------------------------------------------------------------

    def _make_weigh_decision(self, time: float, info: Snapshot,
                             lines: list[str]) -> Decision:
        decision = Decision()
        lines_set = set(lines)

        # -- 1. Trace new FG demands to accumulate active SKUs -----------
        self._trace_new_demands(time)

        # -- 2. Compute shortage ratios -----------------------------------
        ratios = self._compute_shortage_ratios(info)

        # -- 3. Sort by ratio ascending (most urgent first) ---------------
        sorted_skus = sorted(ratios.items(), key=lambda x: x[1])

        # -- 4. Assign lines to SKUs (only lines at decision time) --------
        assigned_lines: set[str] = set()

        for sku, _ratio in sorted_skus:
            eligible = self._sku_lines.get(sku, [])
            free = [l for l in eligible
                    if l not in assigned_lines and l in lines_set]
            if not free:
                continue

            # Skip lines that already have pending orders in their queue
            free = [l for l in free
                    if len(self._production_nodes[l].production_queue) == 0]
            if not free:
                continue

            line_name = self._pick_line(sku, free)
            assigned_lines.add(line_name)

            capacity = self._line_capacity[line_name].get(sku, 0)
            if capacity <= 0:
                continue

            line_info = self._per_line_info[line_name]
            prod_start = self._line_production_start(line_name, time)
            shift_dur = line_info["shift_duration"]

            decision.production_orders.append(ProductionOrder(
                order_id=self._next_oid(),
                sku=sku,
                quantity=capacity,
                activate_time=prod_start,
                expect_time=prod_start + shift_dur,
                node_name=line_name,
            ))

        # -- 5. Transport orders (full tree, per-order scheduling) --------
        if self._transport_mode == "full_tree":
            self._add_full_tree_transport(decision, time)

        return decision

    # ------------------------------------------------------------------
    # Demand handling
    # ------------------------------------------------------------------

    def _issue_demand_orders(self, decision: Decision, time: float) -> None:
        for i, d in enumerate(self._demand_orders):
            if i in self._issued_demand:
                continue
            if d.get("start_time", 0) <= time + 1e-9:
                from_node = d.get("from_node", "fg_storage")
                to_node = d.get("to_node", "sink")
                edge = self.find_edge(from_node, to_node)
                if edge is not None:
                    decision.transport_orders.append(TransportOrder(
                        order_id=self._next_oid(),
                        sku=d["sku"],
                        quantity=d["quantity"],
                        from_node=from_node,
                        to_node=to_node,
                        start_time=time,
                        expect_time=time + 10.0,
                    ))
                    self._issued_demand.add(i)

    # ------------------------------------------------------------------
    # Tracing
    # ------------------------------------------------------------------

    def _trace_new_demands(self, time: float) -> None:
        window = time + 1440.0  # next 24 hours
        while self._next_demand_idx < len(self._demand_orders):
            d = self._demand_orders[self._next_demand_idx]
            if d.get("start_time", 0) > window:
                break
            self._next_demand_idx += 1

            if self._trace_mode == "full":
                self._trace_fg_tree(d["sku"], d["quantity"])
            else:
                self._trace_fg_to_wip(d["sku"], d["quantity"])

    def _trace_fg_tree(self, fg_sku: str, qty: int) -> None:
        """Trace FG → WIP through the BOM tree, adding producible SKUs."""
        if fg_sku not in self._sku_lines:
            return
        self._active_skus.add(fg_sku)

        producers = self._sku_lines.get(fg_sku, [])
        if not producers:
            return

        pnode = self._production_nodes.get(producers[0])
        if pnode is None:
            return

        bom_entry = pnode.bom.get(fg_sku)
        if bom_entry is None:
            return

        for input_sku in bom_entry["inputs"]:
            if input_sku in self._sku_lines:
                self._trace_fg_tree(input_sku, qty)

    def _trace_fg_to_wip(self, fg_sku: str, qty: int) -> None:
        """Trace FG → WIP only (split mode, not yet implemented)."""
        if fg_sku not in self._sku_lines:
            return
        self._active_skus.add(fg_sku)
        producers = self._sku_lines.get(fg_sku, [])
        if not producers:
            return
        pnode = self._production_nodes.get(producers[0])
        if pnode is None:
            return
        bom_entry = pnode.bom.get(fg_sku)
        if bom_entry is None:
            return
        for input_sku in bom_entry["inputs"]:
            if input_sku in self._sku_lines:
                self._active_skus.add(input_sku)

    # ------------------------------------------------------------------
    # Shortage computation
    # ------------------------------------------------------------------

    def _compute_shortage_ratios(
        self, info: Snapshot,
    ) -> dict[str, float]:
        """Return {sku: total_stock / total_safe_stock} for active SKUs."""
        total_stock: dict[str, int] = {}
        for storage, inv in info.storage_stock.items():
            for sku, qty in inv.items():
                total_stock[sku] = total_stock.get(sku, 0) + qty

        ratios: dict[str, float] = {}
        for sku in self._active_skus:
            stock = total_stock.get(sku, 0)
            safe = self._safe_stock_total.get(sku, 1)
            ratios[sku] = stock / safe

        return ratios

    # ------------------------------------------------------------------
    # Line assignment
    # ------------------------------------------------------------------

    def _pick_line(self, sku: str, candidates: list[str]) -> str:
        """Round-robin selection across candidate lines for *sku*."""
        if not candidates:
            raise ValueError(f"No candidate lines for SKU {sku}")
        candidates.sort()
        idx = self._rr_counter.get(sku, 0) % len(candidates)
        self._rr_counter[sku] = idx + 1
        return candidates[idx]

    # ------------------------------------------------------------------
    # Full-tree transport (per-order scheduling)
    # ------------------------------------------------------------------

    def _add_full_tree_transport(
        self, decision: Decision, time: float,
    ) -> None:
        """Issue transport orders per production order.

        Each production order carries its own ``activate_time`` (production
        start) and ``expect_time`` (production end).  Output transports are
        scheduled at production end, input transports at production start,
        and source→storage transports immediately.
        """
        for prod_order in decision.production_orders:
            sku = prod_order.sku
            qty = prod_order.quantity
            node_name = prod_order.node_name
            pnode = self._production_nodes.get(node_name)
            if pnode is None:
                continue

            prod_start = prod_order.activate_time
            prod_end = prod_order.expect_time

            # Output transport: produced SKU → storage (at production end)
            out_node = pnode.downstream_node.node_name
            if sku in self._fg_skus:
                self._add_transport(decision, out_node, "fg_storage", sku, qty, prod_end)
            else:
                # WIP output: route to the pool that the producer drains
                # into (computed by base._wip_pool).
                pool = self._wip_pool.get(sku)
                if pool:
                    self._add_transport(decision, out_node, pool, sku, qty, prod_end)
                else:
                    # No dedicated pool configured for this SKU's producer
                    # (e.g. lineside-only or degenerate topology).  Deliver
                    # to the producer's direct downstream (already = out_node)
                    # so it accumulates locally; this matches a "bypass"
                    # pattern where WIP skips a central store.
                    pass

            # Input transport: BOM inputs → lineside (at production start)
            bom_entry = pnode.bom.get(sku)
            if bom_entry is None:
                continue

            lineside = pnode.upstream_node.node_name

            for input_sku, qty_per in bom_entry["inputs"].items():
                need = qty * qty_per
                supplier = self.find_input_supplier(lineside, input_sku)
                if supplier is None:
                    continue

                # Schedule input transport BEFORE production starts so
                # materials arrive in time.  Lead time = edge transport time
                # + pad buffer (see base.transport_lead_time).
                inp_lead = self.transport_lead_time(supplier, lineside)
                inp_start = max(0.0, prod_start - inp_lead)
                self._add_transport(decision, supplier, lineside,
                                    input_sku, need, inp_start)

                if input_sku in self._sku_lines:
                    # Input is itself a WIP → trigger replenishment of its
                    # own upstream supply chain.

                    if input_sku in self._wip_in_central_storage:
                        # Move the WIP from its accumulation pool into the
                        # lineside's supplier node so this job can consume it.
                        wip_pool = self._wip_pool.get(input_sku)
                        if wip_pool:
                            if supplier != wip_pool:
                                wip_lead = self.transport_lead_time(wip_pool, supplier)
                                wip_start = max(0.0, inp_start - wip_lead)
                                self._add_transport(
                                    decision, wip_pool, supplier,
                                    input_sku, need, wip_start,
                                )

                    # Raw materials for the WIP producer (replenishment)
                    wip_node = self._production_nodes.get(
                        self._sku_lines[input_sku][0]
                    )
                    if wip_node is not None:
                        wip_bom = wip_node.bom.get(input_sku)
                        if wip_bom is not None:
                            wip_lineside = wip_node.upstream_node.node_name
                            for raw_sku, raw_qty_per in wip_bom["inputs"].items():
                                raw_need = need * raw_qty_per
                                raw_supplier = self.find_input_supplier(wip_lineside, raw_sku)
                                if raw_supplier is None:
                                    continue
                                # Source -> raw_supplier happens even earlier
                                raw_in_lead = self.transport_lead_time(raw_supplier, wip_lineside)
                                raw_src_lead = self.transport_lead_time("source", raw_supplier)
                                raw_start = max(0.0, inp_start - raw_in_lead - raw_src_lead)
                                self._add_transport(
                                    decision, raw_supplier, wip_lineside,
                                    raw_sku, raw_need,
                                    max(0.0, inp_start - raw_in_lead),
                                )
                                self._add_transport(
                                    decision, "source", raw_supplier,
                                    raw_sku, raw_need, raw_start,
                                )
                else:
                    # Raw material — replenish from source to the supplier
                    # node (typically raw_material_storage or veg_raw_storage).
                    src_lead = self.transport_lead_time("source", supplier)
                    src_start = max(0.0, inp_start - src_lead)
                    self._add_transport(
                        decision, "source", supplier, input_sku, need, src_start,
                    )

    def _add_transport(
        self, decision: Decision,
        from_node: str, to_node: str,
        sku: str, quantity: int, start_time: float,
    ) -> None:
        edge = self.find_edge(from_node, to_node)
        if edge is None:
            return
        decision.transport_orders.append(TransportOrder(
            order_id=self._next_oid(),
            sku=sku, quantity=quantity,
            from_node=from_node, to_node=to_node,
            start_time=start_time,
            expect_time=start_time + 10.0,
        ))

    # ------------------------------------------------------------------
    # _execute_decision
    # ------------------------------------------------------------------

    def _execute_decision(self, decision: Decision) -> None:
        for order in decision.production_orders:
            node = self._production_nodes.get(order.node_name)
            if node is not None:
                node.add_production_order(order)
            else:
                raise RuntimeError(
                    f"Production order references missing node: "
                    f"'{order.node_name}' for SKU {order.sku}."
                )

        for order in decision.transport_orders:
            edge = self.find_edge(order.from_node, order.to_node)
            if edge is not None:
                edge.add_transport_order(order)
            else:
                raise RuntimeError(
                    f"Transport order references missing edge: "
                    f"'{order.from_node}' -> '{order.to_node}' "
                    f"for SKU {order.sku} qty {order.quantity}."
                )
