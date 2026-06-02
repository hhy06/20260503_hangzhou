import math
from typing import Any
import salabim as sim

from src.management.base import Management, Snapshot, Decision
from src.infrastructure.edge import Edge, TransportOrder
from src.infrastructure.production_node import ProductionOrder
from src.infrastructure.warehouse_node import NodeRole, WarehouseNode


class WeighSafeStockManagement(Management):
    """Weigh-safe-stock management — demand-driven with safe-stock weighted priority.

    Decision cycle
    --------------
    1. Wake at each *decision time* (configurable, default 4h before production start).
    2. Issue FG demand orders (fg_storage → sink).
    3. Trace new FG demands (within next 24h) through the full BOM tree,
       accumulating which SKUs need production.
    4. Compute *shortage ratio* = total_stock / total_safe_stock for each active SKU.
    5. Sort by ratio ascending (most urgent first).
    6. For each production line, assign the most urgent SKU it can produce.
       Quantity = line speed * shift_duration.
    7. Issue production orders (activate_time = upcoming production start).
    8. Issue transport orders for the full supply tree (toggleable via
       *transport_mode*).

    Parameters
    ----------
    safe_stock_config : list[dict]
        Each dict has ``{sku, safe_stock, …}`` — used to compute per-SKU
        total safe stock.
    nodes : dict[str, Component]
    edges : list[Edge]
    demand_orders : list[dict], optional
    production_start_times : list[float], optional
        Minutes-from-day-start for each shift's production start (default
        ``[480, 1200]`` = 08:00, 20:00).
    decision_offset : float
        Minutes before production start when the decision is made (default 240 = 4h).
    shift_duration : float
        Length of one production shift in minutes (default 675 = 11.25h).
    day_start : float
        Simulation time corresponding to midnight / day boundary (default 0).
    trace_mode : str
        ``"full"`` (trace FG→WIP→raw from FG demand) or ``"split"`` (trace
        FG→WIP via FG demand, WIP→raw via WIP demand). Default ``"full"``.
    transport_mode : str
        ``"full_tree"`` (issue all transport orders alongside production) or
        ``"separate"`` (transports handled independently). Default ``"full_tree"``.
    decision_interval : float
        Minimum wake interval (used by base class, overridden by the
        decision-time schedule).
    """

    def __init__(
        self,
        safe_stock_config: list[dict],
        nodes: dict[str, Any],
        edges: list[Edge],
        demand_orders: list[dict] | None = None,
        production_start_times: list[float] | None = None,
        decision_offset: float = 240.0,
        shift_duration: float = 675.0,
        day_start: float = 0.0,
        trace_mode: str = "full",
        transport_mode: str = "full_tree",
        decision_interval: float = 10.0,
        name: str = "WeighSafeStockManagement",
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self.nodes = dict(nodes)
        self.edges = list(edges)
        self._safe_stock_config = list(safe_stock_config)
        self._demand_orders = list(demand_orders or [])
        self._decision_offset = decision_offset
        self._shift_duration = shift_duration
        self._day_start = day_start
        self._trace_mode = trace_mode
        self._transport_mode = transport_mode
        self._production_start_times = sorted(
            production_start_times or [480, 1200]
        )

        self.log: list[dict] = []
        self._next_oid_counter: int = 1

        # -- edge lookup ----------------------------------------------------
        self._edge_map: dict[str, Edge] = {}
        for e in self.edges:
            key = f"{e.from_node.node_name}->{e.to_node.node_name}"
            self._edge_map[key] = e

        # -- production nodes (have a production_queue) ---------------------
        self._production_nodes: dict[str, Any] = {}
        for name, node in self.nodes.items():
            if hasattr(node, "production_queue"):
                self._production_nodes[name] = node

        # -- line → SKU mapping (from BOM) ---------------------------------
        self._line_skus: dict[str, list[str]] = {}
        for name, pnode in self._production_nodes.items():
            self._line_skus[name] = list(pnode.bom.keys())

        # -- SKU → eligible lines -------------------------------------------
        self._sku_lines: dict[str, list[str]] = {}
        for line_name, skus in self._line_skus.items():
            for sku in skus:
                self._sku_lines.setdefault(sku, []).append(line_name)

        # -- line capacity per shift (speed * shift_duration) ---------------
        self._line_capacity: dict[str, dict[str, int]] = {}
        for name, pnode in self._production_nodes.items():
            cap = {}
            for sku, bom_entry in pnode.bom.items():
                speed = bom_entry.get("speed", 0)
                if speed == 0:
                    sku_obj = getattr(pnode, 'sku_registry', None) or {}
                    sku_obj = sku_obj.get(sku) if isinstance(sku_obj, dict) else None
                    if sku_obj and sku_obj.bom_speed > 0:
                        speed = sku_obj.bom_speed
                    else:
                        speed = 1.0
                cap[sku] = max(1, int(speed * self._shift_duration))
            self._line_capacity[name] = cap

        # -- per-SKU total safe stock (sum across all config entries) -------
        self._safe_stock_total: dict[str, int] = {}
        for entry in self._safe_stock_config:
            sku = entry["sku"]
            self._safe_stock_total[sku] = (
                self._safe_stock_total.get(sku, 0) + entry["safe_stock"]
            )

        # -- lineside suppliers (which storage feeds each lineside) ---------
        self._lineside_suppliers: dict[str, str] = {}
        for e in self.edges:
            to_name = e.to_node.node_name
            if to_name.startswith("lineside_"):
                self._lineside_suppliers[to_name] = e.from_node.node_name

        # -- demand / tracing state -----------------------------------------
        self._next_demand_idx = 0
        self._issued_demand: set[int] = set()
        self._active_skus: set[str] = set()

        # -- round-robin counters per SKU -----------------------------------
        self._rr_counter: dict[str, int] = {}

        super().__init__(
            name=name, decision_interval=decision_interval, env=env, **kwargs,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _next_oid(self) -> int:
        self._next_oid_counter += 1
        return self._next_oid_counter

    def find_edge(self, from_node_name: str, to_node_name: str) -> Edge | None:
        return self._edge_map.get(f"{from_node_name}->{to_node_name}")

    def _is_decision_time(self, now: float) -> bool:
        """Return True if *now* is (within epsilon of) a scheduled decision time."""
        day_start = self._day_start
        day_offset = math.floor((now - day_start) / 1440)
        base = day_start + day_offset * 1440
        for prod_start in self._production_start_times:
            dt = base + prod_start - self._decision_offset
            if abs(now - dt) < 1e-6:
                return True
        return False

    def _next_decision_time(self, now: float) -> float:
        """Return the next decision time strictly after *now*."""
        day_start = self._day_start
        days = math.floor((now - day_start) / 1440)

        for day_offset in [days, days + 1, days + 2]:
            base = day_start + day_offset * 1440
            for prod_start in self._production_start_times:
                dt = base + prod_start - self._decision_offset
                if dt > now + 1e-9:
                    return dt
        return now + 1440 * 365

    def _next_production_start(self, decision_time: float) -> float:
        return decision_time + self._decision_offset

    # ------------------------------------------------------------------
    # gather_info
    # ------------------------------------------------------------------

    def gather_info(self) -> Snapshot:
        info = Snapshot(current_time=self.env.now())

        for name, node in self.nodes.items():
            if not isinstance(node, WarehouseNode):
                continue
            if node.role == NodeRole.SOURCE:
                info.source_nodes.add(name)
            elif hasattr(node, "inventory"):
                info.storage_stock[name] = dict(node.inventory)

        for e in self.edges:
            key = f"{e.from_node.node_name}->{e.to_node.node_name}"
            info.edge_pending[key] = list(e.pending_queue)
            info.edge_activated[key] = list(e.activated_queue)

        for name, pnode in self._production_nodes.items():
            info.production_queues[name] = list(pnode.production_queue)

        return info

    # ------------------------------------------------------------------
    # SALABIM process — frequent wake-ups, heavy logic at decision times
    # ------------------------------------------------------------------

    def process(self):
        """Wake every *decision_interval* minutes.

        On every wake-up:
            - Issue due demand orders.
        At decision times (e.g. 4h before each production start):
            - Run full trace + weigh + assign + transport logic.
        """
        while True:
            yield self.hold(self.decision_interval)
            now = self.env.now()

            # Always issue demand orders
            info = self.gather_info()
            demand_decision = Decision()
            self._issue_demand_orders(demand_decision, now)
            self._execute_decision(demand_decision)

            # At decision time: full decision cycle
            if self._is_decision_time(now):
                info = self.gather_info()
                decision = self._make_weigh_decision(now, info)
                self._execute_decision(decision)

    # ------------------------------------------------------------------
    # _make_weigh_decision — the full decision cycle at decision times
    # ------------------------------------------------------------------

    def _make_weigh_decision(self, time: float, info: Snapshot) -> Decision:
        decision = Decision()

        # -- 1. Trace new FG demands to accumulate active SKUs -----------
        self._trace_new_demands(time)

        # -- 2. Compute shortage ratios -----------------------------------
        ratios = self._compute_shortage_ratios(info)

        # -- 3. Sort by ratio ascending (most urgent first) ---------------
        sorted_skus = sorted(ratios.items(), key=lambda x: x[1])

        # -- 4. Assign lines to SKUs --------------------------------------
        assigned_lines: set[str] = set()
        prod_start = self._next_production_start(time)

        for sku, _ratio in sorted_skus:
            eligible_lines = self._sku_lines.get(sku, [])
            free_lines = [l for l in eligible_lines if l not in assigned_lines]
            if not free_lines:
                continue

            line_name = self._pick_line(sku, free_lines)
            assigned_lines.add(line_name)

            capacity = self._line_capacity[line_name].get(sku, 0)
            if capacity <= 0:
                continue

            decision.production_orders.append(ProductionOrder(
                order_id=self._next_oid(),
                sku=sku,
                quantity=capacity,
                activate_time=prod_start,
                expect_time=prod_start + self._shift_duration,
                node_name=line_name,
            ))

        # -- 5. Transport orders (full tree) ------------------------------
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
                # split mode: trace FG→WIP only; WIP→raw handled separately
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
        # Sum stock per SKU across all warehouse nodes
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
    # Full-tree transport
    # ------------------------------------------------------------------

    def _add_full_tree_transport(
        self, decision: Decision, time: float,
    ) -> None:
        """Issue all transport orders for the just-issued production orders.

        Output transports are scheduled to start at production end
        (``prod_start + shift_duration``).  Input transports start at
        ``prod_start`` so materials arrive as production consumes them.
        Source → storage transports start immediately.
        """
        prod_start = self._next_production_start(time)

        # --- Accumulate all transport needs with category tags ------------
        tx_early: dict[tuple[str, str, str], int] = {}      # start now
        tx_at_start: dict[tuple[str, str, str], int] = {}   # start at prod_start
        tx_at_end: dict[tuple[str, str, str], int] = {}     # start at prod_end

        for prod_order in decision.production_orders:
            sku = prod_order.sku
            qty = prod_order.quantity
            node_name = prod_order.node_name
            pnode = self._production_nodes.get(node_name)
            if pnode is None:
                continue

            # Output transport: produced SKU → storage (at production end)
            out_node = pnode.downstream_node.node_name
            if sku.startswith("SKU_"):
                self._accum_tx(tx_at_end, out_node, "fg_storage", sku, qty)
            elif sku.startswith("veg_"):
                self._accum_tx(tx_at_end, out_node, "main_storage_1", sku, qty)
                self._accum_tx(tx_at_end, out_node, "main_storage_2", sku, qty)
            else:
                self._accum_tx(tx_at_end, out_node, "WIP_storage", sku, qty)

            # Input transport: BOM inputs → lineside (at production start)
            bom_entry = pnode.bom.get(sku)
            if bom_entry is None:
                continue

            lineside = pnode.upstream_node.node_name
            supplier = self._lineside_suppliers.get(lineside)

            for input_sku, qty_per in bom_entry["inputs"].items():
                need = qty * qty_per
                if supplier is None:
                    continue

                self._accum_tx(tx_at_start, supplier, lineside, input_sku, need)

                # If input is a WIP, trace WIP_storage → supplier + source → supplier
                if input_sku in self._sku_lines and supplier in (
                    "main_storage_1", "main_storage_2",
                ):
                    self._accum_tx(
                        tx_early, "WIP_storage", supplier, input_sku, need,
                    )
                    wip_node = self._production_nodes.get(
                        self._sku_lines[input_sku][0]
                    )
                    if wip_node is not None:
                        wip_bom = wip_node.bom.get(input_sku)
                        if wip_bom is not None:
                            for raw_sku, raw_qty_per in wip_bom["inputs"].items():
                                raw_need = need * raw_qty_per
                                self._accum_tx(
                                    tx_early, "source", supplier,
                                    raw_sku, raw_need,
                                )
                elif input_sku not in self._sku_lines:
                    self._accum_tx(
                        tx_early, "source", supplier, input_sku, need,
                    )

        # --- Flush with appropriate start times ---------------------------
        prod_end = prod_start + self._shift_duration
        for (fn, tn, sku), qty in tx_early.items():
            self._add_transport(decision, fn, tn, sku, qty, time)
        for (fn, tn, sku), qty in tx_at_start.items():
            self._add_transport(decision, fn, tn, sku, qty, prod_start)
        for (fn, tn, sku), qty in tx_at_end.items():
            self._add_transport(decision, fn, tn, sku, qty, prod_end)

    @staticmethod
    def _accum_tx(
        acc: dict[tuple[str, str, str], int],
        from_node: str,
        to_node: str,
        sku: str,
        qty: int,
    ) -> None:
        key = (from_node, to_node, sku)
        acc[key] = acc.get(key, 0) + qty

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
        now = self.env.now()
        for order in decision.production_orders:
            node = self._production_nodes.get(order.node_name)
            if node is not None:
                self.log.append({
                    "time": now,
                    "type": "order_issued",
                    "order_type": "production",
                    "order_id": order.order_id,
                    "sku": order.sku,
                    "quantity": order.quantity,
                    "node_name": order.node_name,
                    "activate_time": order.activate_time,
                    "expect_time": order.expect_time,
                })
                node.add_production_order(order)
            else:
                raise RuntimeError(
                    f"Production order references missing node: "
                    f"'{order.node_name}' for SKU {order.sku}."
                )

        for order in decision.transport_orders:
            edge = self.find_edge(order.from_node, order.to_node)
            if edge is not None:
                self.log.append({
                    "time": now,
                    "type": "order_issued",
                    "order_type": "transport",
                    "order_id": order.order_id,
                    "sku": order.sku,
                    "quantity": order.quantity,
                    "from_node": order.from_node,
                    "to_node": order.to_node,
                    "start_time": order.start_time,
                    "expect_time": order.expect_time,
                })
                edge.add_transport_order(order)
            else:
                raise RuntimeError(
                    f"Transport order references missing edge: "
                    f"'{order.from_node}' -> '{order.to_node}' "
                    f"for SKU {order.sku} qty {order.quantity}."
                )
