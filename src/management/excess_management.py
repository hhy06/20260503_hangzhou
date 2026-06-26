import math
from typing import Any
import salabim as sim

from src.management.base import Management, Snapshot, Decision
from src.infrastructure.edge import Edge, TransportOrder
from src.infrastructure.production_node import ProductionOrder


class ProductionNeed:
    __slots__ = ("sku", "quantity", "urgency_time", "source_line", "need_id")

    def __init__(
        self,
        sku: str,
        quantity: float,
        urgency_time: float,
        source_line: str = "",
        need_id: int = 0,
    ):
        self.sku = sku
        self.quantity = quantity
        self.urgency_time = urgency_time
        self.source_line = source_line
        self.need_id = need_id


class ExcessManagement(Management):
    """Excess-based production management with three-phase decision cycle.

    Phase 1 (FG): demand orders create equal-quantity production *needs*.
      Each need is first deducted against the line's production_excess.
      If fully covered by excess, the need vanishes.  Otherwise the
      residual quantity stays in the line's need queue.  When a FG line
      reaches its decision time, it picks the most urgent need and
      produces a full shift; output is added to production_excess and
      deducted against remaining needs.

    Phase 2 (WIP): after all FG production is planned, the BOM inputs
      of every scheduled FG shift become WIP *needs*.  These are
      deducted against WIP-line production_excess and queued; WIP
      lines at their decision time produce a full shift for the most
      urgent WIP need.

    Phase 3 (Transport): FG output → fg_storage; WIP output →
      prep_storage (per FG line); raw materials → WIP/FG lineside;
      source → raw_material_storage.

    Parameters
    ----------
    safe_stock_config : list[dict]
        Per-SKU safe-stock thresholds (used for urgency ranking).
    nodes : dict[str, Component]
    edges : list[Edge]
    demand_orders : list[dict], optional
        FG demand schedule (sku, quantity, start_time, …).
    lookahead_window : float
        How far ahead (minutes) to scan demands for pre-ordering.
        Default 2880 (2 days).
    decision_interval : float
        Minimum wake interval for demand processing.
    """

    def __init__(
        self,
        safe_stock_config: list[dict],
        nodes: dict[str, Any],
        edges: list[Edge],
        demand_orders: list[dict] | None = None,
        lookahead_window: float = 2880.0,
        decision_interval: float = 10.0,
        name: str = "ExcessManagement",
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self._safe_stock_config = list(safe_stock_config)
        self._demand_orders = list(demand_orders or [])
        self._lookahead_window = lookahead_window

        self._next_oid_counter: int = 1
        self._next_need_id: int = 1

        self._issued_demand: set[int] = set()
        self._next_demand_idx = 0

        super().__init__(
            nodes=nodes, edges=edges,
            name=name, decision_interval=decision_interval, env=env, **kwargs,
        )

        # -- per-line shift info (from ProductionNode attributes) ----------
        self._per_line_info: dict[str, dict] = {}
        for n, pnode in self._production_nodes.items():
            sd = pnode.shift_duration
            do = pnode.decision_offset
            pst = pnode.production_start_times
            if sd is None or do is None or pst is None:
                raise ValueError(
                    f"Production node '{n}' missing shift config "
                    f"(shift_duration={sd}, decision_offset={do}, "
                    f"production_start_times={pst})."
                )
            self._per_line_info[n] = {
                "shift_duration": float(sd),
                "decision_offset": float(do),
                "production_start_times": sorted(float(t) for t in pst),
            }

        # -- line → SKU mapping (from BOM) ---------------------------------
        self._line_skus: dict[str, list[str]] = {}
        for n, pnode in self._production_nodes.items():
            self._line_skus[n] = list(pnode.bom.keys())

        # -- SKU → eligible lines -------------------------------------------
        self._sku_lines: dict[str, list[str]] = {}
        for ln, skus in self._line_skus.items():
            for sku in skus:
                self._sku_lines.setdefault(sku, []).append(ln)

        # -- line capacity per shift (speed * shift_duration) ---------------
        self._line_capacity: dict[str, dict[str, int]] = {}
        for n, pnode in self._production_nodes.items():
            cap = {}
            sd = self._per_line_info[n]["shift_duration"]
            for sku, bom_entry in pnode.bom.items():
                speed = bom_entry.get("speed", 0)
                if speed == 0:
                    sku_obj = getattr(pnode, "sku_registry", None) or {}
                    sku_obj = sku_obj.get(sku) if isinstance(sku_obj, dict) else None
                    if sku_obj and sku_obj.bom_speed > 0:
                        speed = sku_obj.bom_speed
                    else:
                        speed = 1.0
                cap[sku] = max(1, int(speed * sd))
            self._line_capacity[n] = cap

        # -- per-SKU total safe stock ----------------------------------------
        self._safe_stock_total: dict[str, int] = {}
        for entry in self._safe_stock_config:
            sku = entry["sku"]
            self._safe_stock_total[sku] = (
                self._safe_stock_total.get(sku, 0) + entry["safe_stock"]
            )

        # -- need queues per line --------------------------------------------
        # Each entry is (sku, remaining_quantity, earliest_urgency_time)
        self._need_queues: dict[str, dict[str, dict]] = {}
        for n in self._production_nodes:
            self._need_queues[n] = {}

        # -- round-robin position per line -----------------------------------
        self._rr_sku_pos: dict[str, int] = {}

        # -- classify lines: FG vs WIP ----------------------------------------
        # A line is FG if at least one of its BOM output SKUs is in
        # self._fg_skus (computed by base class from fg_storage topology).
        self._fg_lines: set[str] = set()
        self._wip_lines: set[str] = set()
        for n, pnode in self._production_nodes.items():
            is_fg = any(sku in self._fg_skus for sku in pnode.bom)
            if is_fg:
                self._fg_lines.add(n)
            else:
                self._wip_lines.add(n)

        # -- round-robin counters per SKU ------------------------------------
        self._rr_counter: dict[str, int] = {}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _next_oid(self) -> int:
        self._next_oid_counter += 1
        return self._next_oid_counter

    def _next_nid(self) -> int:
        self._next_need_id += 1
        return self._next_need_id

    # ------------------------------------------------------------------
    # Per-line decision-time helpers (same as WeighSafeStockManagement)
    # ------------------------------------------------------------------

    def _line_decision_times(self, line_name: str, now: float) -> list[float]:
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
        for dt in self._line_decision_times(line_name, now):
            if abs(now - dt) < 1e-6:
                return True
        return False

    def _lines_at_decision_time(self, now: float) -> list[str]:
        return [
            name for name in self._per_line_info
            if self._is_line_decision_time(name, now)
        ]

    def _line_next_decision_time(self, line_name: str, now: float) -> float:
        return min(
            dt for dt in self._line_decision_times(line_name, now)
            if dt > now + 1e-9
        )

    def _next_decision_time(self, now: float) -> float:
        next_dt = float("inf")
        for line_name in self._per_line_info:
            dt = self._line_next_decision_time(line_name, now)
            if dt < next_dt:
                next_dt = dt
        return next_dt

    def _line_production_start(self, line_name: str, decision_time: float) -> float:
        info = self._per_line_info[line_name]
        for dt in self._line_decision_times(line_name, decision_time):
            if abs(decision_time - dt) < 1e-6:
                shift_idx = self._line_decision_times(line_name, decision_time).index(dt)
                prod_starts = info["production_start_times"]
                day_off = shift_idx // len(prod_starts)
                ps_idx = shift_idx % len(prod_starts)
                base = math.floor(decision_time / 1440) * 1440
                return base + day_off * 1440 + prod_starts[ps_idx]
        return decision_time + info["decision_offset"]

    # ------------------------------------------------------------------
    # excess deduction
    # ------------------------------------------------------------------

    def _deduct_excess(
        self, line_name: str, sku: str, quantity: float,
    ) -> float:
        """Deduct *quantity* against the line's production_excess for *sku*.

        Returns the remaining (uncovered) quantity after deduction.
        """
        pnode = self._production_nodes[line_name]
        excess = pnode.production_excess.get(sku, 0.0)
        if excess >= quantity:
            pnode.production_excess[sku] = excess - quantity
            return 0.0
        else:
            remaining = quantity - excess
            pnode.production_excess[sku] = 0.0
            return remaining

    # ------------------------------------------------------------------
    # need queue management
    # ------------------------------------------------------------------

    def _add_need(self, line_name: str, sku: str, quantity: float, urgency_time: float) -> None:
        remaining = self._deduct_excess(line_name, sku, quantity)
        if remaining <= 1e-9:
            return
        queue = self._need_queues[line_name]
        if sku in queue:
            entry = queue[sku]
            entry["quantity"] += remaining
            entry["urgency_time"] = min(entry["urgency_time"], urgency_time)
        else:
            queue[sku] = {"quantity": remaining, "urgency_time": urgency_time}

    def _pick_producible_need(
        self, line_name: str, info: Snapshot,
    ) -> str | None:
        queue = self._need_queues[line_name]
        if not queue:
            return None
        pnode = self._production_nodes[line_name]
        lineside = pnode.upstream_node.node_name
        lineside_stock = info.storage_stock.get(lineside, {})

        skus = sorted(queue.keys())
        start_pos = self._rr_sku_pos.get(line_name, 0) % len(skus)

        for offset in range(len(skus)):
            pos = (start_pos + offset) % len(skus)
            sku = skus[pos]
            bom_entry = pnode.bom.get(sku)
            if bom_entry is None:
                continue
            has_materials = True
            for input_sku, qty_per in bom_entry["inputs"].items():
                required = queue[sku]["quantity"] * qty_per
                available = lineside_stock.get(input_sku, 0)
                if available < required * 0.5:
                    has_materials = False
                    break
            if has_materials:
                self._rr_sku_pos[line_name] = (pos + 1) % len(skus)
                return sku

        return skus[start_pos]

    # ------------------------------------------------------------------
    # SALABIM process — dynamic scheduling
    # ------------------------------------------------------------------

    def process(self):
        """Periodic loop: demand issuance + proactive transport + production."""
        while True:
            now = self.env.now()

            info = self.gather_info()

            demand_decision = Decision()
            self._issue_demand_orders(demand_decision, now, info)
            self._scan_demands(now)
            self._issue_proactive_transport(demand_decision, now, info)
            self._issue_production_orders(demand_decision, now, info)
            self._execute_decision(demand_decision)

            next_dt = self._next_decision_time(now)
            next_wake = min(now + self.decision_interval, next_dt)
            if next_wake <= now + 1e-9:
                next_wake = now + self.decision_interval
            yield self.hold(next_wake - now)

    # ------------------------------------------------------------------
    # proactive transport (WIP/raw → FG lineside based on FG needs)
    # ------------------------------------------------------------------

    def _issue_proactive_transport(
        self, decision: Decision, time: float, info: Snapshot,
    ) -> None:
        for line_name in self._fg_lines:
            queue = self._need_queues.get(line_name, {})
            if not queue:
                continue
            pnode = self._production_nodes[line_name]
            lineside = pnode.upstream_node.node_name
            lineside_stock = info.storage_stock.get(lineside, {})
            prep = self._fert_prep.get(line_name)

            for sku, entry in queue.items():
                need_qty = entry["quantity"]
                urgency_time = entry["urgency_time"]
                bom_entry = pnode.bom.get(sku)
                if bom_entry is None:
                    continue
                for input_sku, qty_per in bom_entry["inputs"].items():
                    needed_total = int(need_qty * qty_per)
                    if needed_total <= 0:
                        continue
                    already_at_lineside = lineside_stock.get(input_sku, 0)
                    shortfall = needed_total - already_at_lineside
                    if shortfall <= 0:
                        continue

                    if prep:
                        prep_stock = info.storage_stock.get(prep, {}).get(input_sku, 0)
                        from_prep = min(shortfall, prep_stock)
                        prep_lead = self.transport_lead_time(prep, lineside)
                        prep_start = max(0.0, urgency_time - prep_lead)
                        if from_prep > 0:
                            self._add_transport(
                                decision, prep, lineside,
                                input_sku, from_prep, prep_start,
                            )
                            shortfall -= from_prep
                            if shortfall <= 0:
                                continue

                        pool_needed = shortfall
                        wip_pool = self._wip_pool.get(input_sku)
                        if wip_pool:
                            pool_stock = info.storage_stock.get(wip_pool, {}).get(input_sku, 0)
                            from_pool = min(pool_needed, pool_stock)
                            if from_pool > 0:
                                pool_lead = self.transport_lead_time(wip_pool, prep)
                                pool_start = max(0.0, prep_start - pool_lead)
                                self._add_transport(
                                    decision, wip_pool, prep,
                                    input_sku, from_pool, pool_start,
                                )
                                pool_needed -= from_pool

                        if pool_needed > 0 and input_sku not in self._sku_lines:
                            src_lead = self.transport_lead_time("source", prep)
                            src_start = max(0.0, prep_start - src_lead)
                            self._add_transport(
                                decision, "source", prep,
                                input_sku, pool_needed, src_start,
                            )

                        remaining_to_lineside = shortfall
                        if remaining_to_lineside > 0:
                            later_start = prep_start + 20.0
                            self._add_transport(
                                decision, prep, lineside,
                                input_sku, remaining_to_lineside, later_start,
                            )
                    else:
                        supplier = self.find_input_supplier(lineside, input_sku)
                        if supplier is None:
                            continue
                        supplier_stock = info.storage_stock.get(supplier, {}).get(input_sku, 0)
                        if supplier in info.source_nodes:
                            ship_qty = shortfall
                        else:
                            ship_qty = min(shortfall, supplier_stock)
                        if ship_qty <= 0:
                            continue
                        inp_lead = self.transport_lead_time(supplier, lineside)
                        inp_start = max(0.0, urgency_time - inp_lead)
                        self._add_transport(
                            decision, supplier, lineside,
                            input_sku, ship_qty, inp_start,
                        )

        self._flush_output_buffers(decision, time, info)

    def _flush_output_buffers(
        self, decision: Decision, time: float, info: Snapshot,
    ) -> None:
        for line_name in self._fg_lines:
            pnode = self._production_nodes[line_name]
            out_node = pnode.downstream_node.node_name
            out_stock = info.storage_stock.get(out_node, {})
            if not out_stock:
                continue
            fg_dest = "fg_storage"
            for sku, qty in out_stock.items():
                if qty <= 0:
                    continue
                self._add_transport(
                    decision, out_node, fg_dest,
                    sku, qty, time,
                )

        for line_name in self._wip_lines:
            pnode = self._production_nodes[line_name]
            out_node = pnode.downstream_node.node_name
            out_stock = info.storage_stock.get(out_node, {})
            if not out_stock:
                continue
            for sku, qty in out_stock.items():
                if qty <= 0:
                    continue
                wip_pool = self._wip_pool.get(sku)
                if wip_pool:
                    self._add_transport(
                        decision, out_node, wip_pool,
                        sku, qty, time,
                    )

    # ------------------------------------------------------------------
    # demand issuance
    # ------------------------------------------------------------------

    def _issue_demand_orders(
        self, decision: Decision, time: float, info: Snapshot,
    ) -> None:
        for i, d in enumerate(self._demand_orders):
            if i in self._issued_demand:
                continue
            if d.get("start_time", 0) <= time + 1e-9:
                from_node = d.get("from_node", "fg_storage")
                to_node = d.get("to_node", "sink")
                edge = self.find_edge(from_node, to_node)
                if edge is not None:
                    fg_stock = info.storage_stock.get(from_node, {}).get(d["sku"], 0)
                    ship_qty = min(d["quantity"], fg_stock)
                    if ship_qty <= 0:
                        continue
                    decision.transport_orders.append(TransportOrder(
                        order_id=self._next_oid(),
                        sku=d["sku"],
                        quantity=ship_qty,
                        from_node=from_node,
                        to_node=to_node,
                        start_time=time,
                        expect_time=time + 10.0,
                    ))
                    self._issued_demand.add(i)

    # ------------------------------------------------------------------
    # demand scanning → FG production needs
    # ------------------------------------------------------------------

    def _scan_demands(self, time: float) -> None:
        window = time + self._lookahead_window
        while self._next_demand_idx < len(self._demand_orders):
            d = self._demand_orders[self._next_demand_idx]
            if d.get("start_time", 0) > window:
                break
            self._next_demand_idx += 1

            sku = d["sku"]
            qty = d["quantity"]

            eligible = self._sku_lines.get(sku, [])
            if not eligible:
                continue

            idx = self._rr_counter.get(sku, 0) % len(eligible)
            line_name = eligible[idx]
            self._rr_counter[sku] = idx + 1

            self._add_need(line_name, sku, float(qty), d.get("start_time", 0))

            if qty > 0 and line_name in self._fg_lines:
                fg_pnode = self._production_nodes[line_name]
                bom_entry = fg_pnode.bom.get(sku)
                if bom_entry is not None:
                    for input_sku, qty_per in bom_entry["inputs"].items():
                        if input_sku not in self._sku_lines:
                            continue
                        wip_need_qty = qty * qty_per
                        wip_lines = self._sku_lines[input_sku]
                        widx = self._rr_counter.get(input_sku, 0) % len(wip_lines)
                        wl = wip_lines[widx]
                        self._rr_counter[input_sku] = widx + 1
                        self._add_need(wl, input_sku, float(wip_need_qty), d.get("start_time", 0))

    # ------------------------------------------------------------------
    # production order issuance (every wake-up)
    # ------------------------------------------------------------------

    def _issue_production_orders(
        self, decision: Decision, time: float, info: Snapshot,
    ) -> None:
        fg_production_orders: list[ProductionOrder] = []
        wip_production_orders: list[ProductionOrder] = []

        for line_name in self._fg_lines:
            pnode = self._production_nodes[line_name]
            if len(pnode.production_queue) >= 2:
                continue
            sku = self._pick_producible_need(line_name, info)
            if sku is None:
                continue
            capacity = self._line_capacity[line_name].get(sku, 0)
            if capacity <= 0:
                continue
            need_qty = self._need_queues[line_name][sku]["quantity"]

            surplus = float(capacity - need_qty)
            if surplus > 0:
                pnode.production_excess[sku] = (
                    pnode.production_excess.get(sku, 0.0) + surplus
                )

            line_info = self._per_line_info[line_name]
            prod_starts = line_info["production_start_times"]
            base = math.floor(time / 1440) * 1440
            best_start = float("inf")
            for day_off in (0, 1, 2):
                for ps in prod_starts:
                    candidate = base + day_off * 1440 + ps
                    if candidate >= time - 1e-9 and candidate < best_start:
                        best_start = candidate
            if best_start == float("inf"):
                best_start = time + line_info["decision_offset"]

            order = ProductionOrder(
                order_id=self._next_oid(),
                sku=sku,
                quantity=capacity,
                activate_time=best_start,
                expect_time=best_start + line_info["shift_duration"],
                node_name=line_name,
            )
            decision.production_orders.append(order)
            fg_production_orders.append(order)

            self._need_queues[line_name][sku]["quantity"] -= capacity
            if self._need_queues[line_name][sku]["quantity"] <= 1e-9:
                del self._need_queues[line_name][sku]

        for line_name in self._wip_lines:
            pnode = self._production_nodes[line_name]
            if len(pnode.production_queue) >= 2:
                continue
            sku = self._pick_producible_need(line_name, info)
            if sku is None:
                continue
            capacity = self._line_capacity[line_name].get(sku, 0)
            if capacity <= 0:
                continue

            surplus = float(capacity - self._need_queues[line_name][sku]["quantity"])
            if surplus > 0:
                pnode.production_excess[sku] = (
                    pnode.production_excess.get(sku, 0.0) + surplus
                )

            line_info = self._per_line_info[line_name]
            prod_starts = line_info["production_start_times"]
            base = math.floor(time / 1440) * 1440
            best_start = float("inf")
            for day_off in (0, 1, 2):
                for ps in prod_starts:
                    candidate = base + day_off * 1440 + ps
                    if candidate >= time - 1e-9 and candidate < best_start:
                        best_start = candidate
            if best_start == float("inf"):
                best_start = time + line_info["decision_offset"]

            order = ProductionOrder(
                order_id=self._next_oid(),
                sku=sku,
                quantity=capacity,
                activate_time=best_start,
                expect_time=best_start + line_info["shift_duration"],
                node_name=line_name,
            )
            decision.production_orders.append(order)
            wip_production_orders.append(order)

            self._need_queues[line_name][sku]["quantity"] -= capacity
            if self._need_queues[line_name][sku]["quantity"] <= 1e-9:
                del self._need_queues[line_name][sku]

        self._add_transport_orders(
            decision, time, fg_production_orders, wip_production_orders,
        )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # transport order generation
    # ------------------------------------------------------------------

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

    def _add_transport_orders(
        self,
        decision: Decision,
        time: float,
        fg_production_orders: list[ProductionOrder],
        wip_production_orders: list[ProductionOrder],
    ) -> None:
        # -- FG output → fg_storage ----------------------------------------
        for prod_order in fg_production_orders:
            pnode = self._production_nodes[prod_order.node_name]
            out_node = pnode.downstream_node.node_name
            self._add_transport(
                decision, out_node, "fg_storage",
                prod_order.sku, prod_order.quantity, prod_order.expect_time,
            )

        # -- WIP output → prep_storage --------------------------------------
        for prod_order in wip_production_orders:
            pnode = self._production_nodes[prod_order.node_name]
            out_node = pnode.downstream_node.node_name
            wip_pool = self._wip_pool.get(prod_order.sku)
            if wip_pool:
                self._add_transport(
                    decision, out_node, wip_pool,
                    prod_order.sku, prod_order.quantity, prod_order.expect_time,
                )
            else:
                fg_lines_needing = []
                for fg_line in self._fg_lines:
                    fg_pnode = self._production_nodes[fg_line]
                    bom_entry = fg_pnode.bom.get(
                        next(iter(fg_pnode.bom.keys())), None
                    )
                    if bom_entry and prod_order.sku in bom_entry["inputs"]:
                        fg_lines_needing.append(fg_line)

                prep_targets = set()
                for fl in fg_lines_needing:
                    prep = self._fert_prep.get(fl)
                    if prep:
                        prep_targets.add(prep)
                    else:
                        for e in self.edges:
                            if e.to_node.node_name.startswith("lineside_") and \
                               e.from_node.node_name.startswith("prep_storage"):
                                prep_targets.add(e.from_node.node_name)

                for prep in prep_targets:
                    self._add_transport(
                        decision, out_node, prep,
                        prod_order.sku, prod_order.quantity, prod_order.expect_time,
                    )

        # -- WIP BOM input: raw → WIP lineside -----------------------------
        for prod_order in wip_production_orders:
            pnode = self._production_nodes[prod_order.node_name]
            bom_entry = pnode.bom.get(prod_order.sku)
            if bom_entry is None:
                continue
            lineside = pnode.upstream_node.node_name
            prod_start = prod_order.activate_time

            for input_sku, qty_per in bom_entry["inputs"].items():
                need = int(prod_order.quantity * qty_per)
                if need <= 0:
                    continue
                supplier = self.find_input_supplier(lineside, input_sku)
                if supplier is None:
                    continue
                inp_lead = self.transport_lead_time(supplier, lineside)
                inp_start = max(0.0, prod_start - inp_lead)
                self._add_transport(
                    decision, supplier, lineside,
                    input_sku, need, inp_start,
                )
                src_lead = self.transport_lead_time("source", supplier)
                src_start = max(0.0, inp_start - src_lead)
                self._add_transport(
                    decision, "source", supplier,
                    input_sku, need, src_start,
                )

        # -- FG BOM input: raw/WIP → FG lineside ---------------------------
        for prod_order in fg_production_orders:
            pnode = self._production_nodes[prod_order.node_name]
            bom_entry = pnode.bom.get(prod_order.sku)
            if bom_entry is None:
                continue
            lineside = pnode.upstream_node.node_name
            prod_start = prod_order.activate_time

            for input_sku, qty_per in bom_entry["inputs"].items():
                need = int(prod_order.quantity * qty_per)
                if need <= 0:
                    continue
                supplier = self.find_input_supplier(lineside, input_sku)
                if supplier is None:
                    continue
                inp_lead = self.transport_lead_time(supplier, lineside)
                inp_start = max(0.0, prod_start - inp_lead)
                self._add_transport(
                    decision, supplier, lineside,
                    input_sku, need, inp_start,
                )
                if input_sku not in self._sku_lines:
                    src_lead = self.transport_lead_time("source", supplier)
                    src_start = max(0.0, inp_start - src_lead)
                    self._add_transport(
                        decision, "source", supplier,
                        input_sku, need, src_start,
                    )

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
