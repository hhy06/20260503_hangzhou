"""Trace management — demand-driven supply chain orchestration.

A :class:`TraceManagement` holds a list of scheduled FG demand orders.
Each decision cycle it picks newly-due demands and generates the full
upstream supply tree:

    demand FG -> FG production -> BOM inputs -> WIP production ->
    raw materials -> source inbound

All orders carry the current decision-cycle time so they queue and
execute as capacity allows, keeping the system statistically static.
"""

import math
from typing import Any
import salabim as sim

from src.management.base import Management, Snapshot, Decision
from src.infrastructure.edge import Edge, TransportOrder
from src.infrastructure.production_node import ProductionOrder
from src.infrastructure.warehouse_node import NodeRole, WarehouseNode


class TraceManagement(Management):
    """Demand-driven management that generates a complete supply tree.

    On each decision cycle, for every newly-due demand order this
    manager creates:

    * the FG transport (storage -> sink),
    * a FG production order (round-robin across eligible lines),
    * all upstream transport and production orders (WIP, raw materials,
      source inbound).

    Parameters
    ----------
    nodes : dict[str, Component]
    edges : list[Edge]
    demand_orders : list[dict], optional
        Each dict requires ``sku``, ``quantity``, ``from_node``,
        ``to_node``, ``start_time``.
    decision_interval : float
    name : str, optional
    env : sim.Environment | None
    """

    def __init__(
        self,
        nodes: dict[str, Any],
        edges: list[Edge],
        demand_orders: list[dict] | None = None,
        decision_interval: float = 10.0,
        name: str = "TraceManagement",
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self.nodes = dict(nodes)
        self.edges = list(edges)
        self._demand_orders = list(demand_orders or [])
        self._next_demand_idx = 0

        # edge lookup
        self._edge_map: dict[str, Edge] = {}
        for e in self.edges:
            key = f"{e.from_node.node_name}->{e.to_node.node_name}"
            self._edge_map[key] = e

        # production nodes (have a production_queue)
        self._production_nodes: dict[str, Any] = {}
        for name, node in self.nodes.items():
            if hasattr(node, "production_queue"):
                self._production_nodes[name] = node

        # sku -> [producer node names] derived from BOMs
        self._producers_of_sku: dict[str, list[str]] = {}
        for name, pnode in self._production_nodes.items():
            for out_sku in pnode.bom:
                self._producers_of_sku.setdefault(out_sku, []).append(name)

        # lineside -> the warehouse that feeds it (from edges)
        self._lineside_suppliers: dict[str, str] = {}
        for e in self.edges:
            to_name = e.to_node.node_name
            if to_name.startswith("lineside_"):
                self._lineside_suppliers[to_name] = e.from_node.node_name

        # round-robin counters per SKU
        self._rr_counter: dict[str, int] = {}
        self._next_job_id: int = 1
        self.log: list[dict] = []

        super().__init__(
            name=name, decision_interval=decision_interval, env=env, **kwargs,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def find_edge(self, from_node_name: str, to_node_name: str) -> Edge | None:
        """Locate the edge between two named nodes."""
        return self._edge_map.get(f"{from_node_name}->{to_node_name}")

    def _pick_producer(self, sku: str, candidates: list[str]) -> str | None:
        """Round-robin selection across candidate production nodes."""
        if not candidates:
            return None
        idx = self._rr_counter.get(sku, 0) % len(candidates)
        self._rr_counter[sku] = idx + 1
        return candidates[idx]

    def _add_transport(
        self, decision: Decision,
        from_node: str, to_node: str,
        sku: str, quantity: int, now: float,
    ) -> None:
        """Append a transport order if the edge exists.

        The quantity is rounded up to the next full pallet so that the
        order matches what the edge's ``_execute_order`` will debit
        (preventing the order from being permanently skipped when the
        available stock is less than the pallet-rounded requirement).
        """
        edge = self.find_edge(from_node, to_node)
        if edge is None:
            if hasattr(self, "log"):
                self.log.append({
                    "time": self.env.now(),
                    "type": "transport_order_dropped",
                    "sku": sku,
                    "quantity": quantity,
                    "from": from_node,
                    "to": to_node,
                    "reason": "no_edge",
                })
            return
        ipp = edge.from_node.conversion_factors.get(sku, 1)
        num_pallets = math.ceil(quantity / ipp)
        pallet_qty = num_pallets * ipp
        decision.transport_orders.append(TransportOrder(
            sku=sku, quantity=pallet_qty,
            from_node=from_node, to_node=to_node,
            start_time=now, expect_time=now,
        ))

    def _add_production(
        self, decision: Decision,
        node_name: str, sku: str, quantity: int, now: float,
    ) -> None:
        """Append a production order with a fresh job id.

        The quantity is rounded up to the next full pallet so that
        ``_add_transport`` ordering from the output buffer and the
        actual production output stay in sync.
        """
        node = self._production_nodes.get(node_name)
        ipp = 1
        if node is not None:
            ipp = node.output_conversion_factors.get(sku, 1)
        pallet_qty = math.ceil(quantity / ipp) * ipp
        decision.production_orders.append(ProductionOrder(
            job_id=self._next_job_id,
            sku=sku, quantity=pallet_qty,
            activate_time=now, expect_time=now,
            node_name=node_name,
        ))
        self._next_job_id += 1

    # ------------------------------------------------------------------
    # gather_info
    # ------------------------------------------------------------------

    def gather_info(self) -> Snapshot:
        """Full snapshot of stock levels, edge queues, and production queues."""
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
    # make_decisions — pre-compute all upstream orders on first call
    # ------------------------------------------------------------------

    def make_decisions(self, time: float, info: Snapshot) -> Decision:
        """Pre-compute all upstream orders from all scheduled demands.

        Two-phase approach:

        1. **Accumulate** all transport/production needs across *every*
           demand order into ``tx_acc`` / ``prod_acc``.

        2. **Two-pass rounding**: raw MS → lineside quantities are each
           individually pallet-rounded.  Source → MS transport quantities
           are then set to the **sum of the rounded** MS → lineside
           quantities so that total debits never exceed what source
           delivers to the shared storage.

        Subsequent calls return an empty ``Decision``.
        """
        if self._next_demand_idx >= len(self._demand_orders):
            return Decision()

        decision = Decision()
        t = time

        tx_acc: dict[tuple[str, str, str], int] = {}
        prod_acc: dict[tuple[str, str], int] = {}

        for demand in self._demand_orders:
            sku = demand["sku"]
            qty = demand["quantity"]

            self._accum_tx(
                tx_acc,
                demand["from_node"], demand["to_node"],
                sku, qty,
            )
            self._accum_fg_tree(tx_acc, prod_acc, sku, qty, t)

        self._next_demand_idx = len(self._demand_orders)  # mark consumed

        # -- Pass 1: flush non-source transport + all production ----------
        # MS → lineside & WIP → MS & output → WIP orders get their rounded
        # quantity right away.  Source → MS orders are deferred to Pass 2.
        source_tx: dict[tuple[str, str, str], int] = {}
        for (fn, tn, sku), qty in tx_acc.items():
            if fn == "source":
                source_tx[(fn, tn, sku)] = qty
            else:
                self._add_transport(decision, fn, tn, sku, qty, t)

        for (node_name, sku), qty in prod_acc.items():
            self._add_production(decision, node_name, sku, qty, t)

        # -- Pass 2: source → MS orders using rounded totals --------------
        # Source is infinite, but MS has finite capacity.  We round each
        # individual source → MS → lineside chain so that the total source
        # delivery covers all pallet-rounded MS → lineside debits.
        # Reverse-map: for each (MS, sku) collect all lineside destinations.
        ms_to_lineside: dict[tuple[str, str], list[str]] = {}
        for (fn, tn, sku) in tx_acc:
            if fn != "source" and tn.startswith("lineside_"):
                ms_to_lineside.setdefault((fn, sku), []).append(tn)

        # For each (source, MS, sku), compute rounded total = sum of
        # individual MS → lineside rounded quantities.
        source_needs: dict[tuple[str, str, str], int] = {}
        for (source_name, ms_name, sku), raw_qty in source_tx.items():
            ms_linesides = ms_to_lineside.get((ms_name, sku), [])
            if ms_linesides:
                # Sum of rounded MS → lineside debits
                total_rounded = 0
                for ls in ms_linesides:
                    rounded = self._rounded_qty(ms_name, ls, sku,
                                                 tx_acc.get((ms_name, ls, sku), 0))
                    total_rounded += rounded
                source_needs[(source_name, ms_name, sku)] = total_rounded
            else:
                # No MS → lineside route — send raw qty
                source_needs[(source_name, ms_name, sku)] = self._rounded_qty(
                    source_name, ms_name, sku, raw_qty,
                )

        for (fn, tn, sku), qty in source_needs.items():
            self._add_transport(decision, fn, tn, sku, qty, t)

        return decision

    def _rounded_qty(self, from_node: str, to_node: str,
                     sku: str, qty: int) -> int:
        """Return the pallet-rounded transport quantity, or 0 if no edge."""
        edge = self.find_edge(from_node, to_node)
        if edge is None:
            return 0
        ipp = edge.from_node.conversion_factors.get(sku, 1)
        return math.ceil(qty / ipp) * ipp

    # ------------------------------------------------------------------
    # accumulators (per-decision-cycle batching)
    # ------------------------------------------------------------------

    @staticmethod
    def _accum_tx(
        acc: dict[tuple[str, str, str], int],
        from_node: str, to_node: str, sku: str, qty: int,
    ) -> None:
        key = (from_node, to_node, sku)
        acc[key] = acc.get(key, 0) + qty

    @staticmethod
    def _accum_prod(
        acc: dict[tuple[str, str], int],
        node_name: str, sku: str, qty: int,
    ) -> None:
        key = (node_name, sku)
        acc[key] = acc.get(key, 0) + qty

    # ------------------------------------------------------------------
    # tree generators (batched via accumulators)
    # ------------------------------------------------------------------

    def _accum_fg_tree(
        self,
        tx_acc: dict[tuple[str, str, str], int],
        prod_acc: dict[tuple[str, str], int],
        fg_sku: str, qty: int, t: float,
    ) -> None:
        """Accumulate FG production + BOM + WIP + raw-material orders."""
        producers = self._producers_of_sku.get(fg_sku)
        if not producers:
            return

        noodle = self._pick_producer(fg_sku, producers)
        if noodle is None:
            return
        noodle_node = self._production_nodes[noodle]
        lineside = noodle_node.upstream_node.node_name
        ms = self._lineside_suppliers.get(lineside)
        if ms is None:
            return

        # FG production
        self._accum_prod(prod_acc, noodle, fg_sku, qty)

        # Push FG from noodle output buffer to fg_storage
        self._accum_tx(
            tx_acc,
            noodle_node.downstream_node.node_name,
            "fg_storage", fg_sku, qty,
        )

        # For each BOM input of this FG SKU
        bom = noodle_node.bom[fg_sku]
        for input_sku, qty_per in bom["inputs"].items():
            need = qty * qty_per

            # Transport: main_storage -> noodle lineside
            self._accum_tx(tx_acc, ms, lineside, input_sku, need)

            if input_sku in self._producers_of_sku:
                self._accum_wip_tree(tx_acc, prod_acc, input_sku, need, ms)
            else:
                # Raw material / packaging
                self._accum_tx(tx_acc, "source", ms, input_sku, need)

    def _pallet_qty(self, sku: str, quantity: int) -> int:
        """Round *quantity* up to the next full pallet for *sku*."""
        # Pallet sizes are uniform for each SKU across the system.
        # Use any production node's output_conversion_factors as source of truth.
        ipp = 100  # default (most SKUs)
        for pnode in self._production_nodes.values():
            cf = pnode.output_conversion_factors.get(sku)
            if cf is not None:
                ipp = cf
                break
        return math.ceil(quantity / ipp) * ipp

    def _accum_wip_tree(
        self,
        tx_acc: dict[tuple[str, str, str], int],
        prod_acc: dict[tuple[str, str], int],
        wip_sku: str, qty: int, target_ms: str,
    ) -> None:
        """Accumulate WIP production + raw-material orders for one WIP SKU."""
        producers = self._producers_of_sku.get(wip_sku, [])
        if not producers:
            return

        producer = self._pick_producer(wip_sku, producers)
        if producer is None:
            return
        prod_node = self._production_nodes[producer]
        out_node = prod_node.downstream_node.node_name
        lineside = prod_node.upstream_node.node_name
        supplier = self._lineside_suppliers.get(lineside)

        # Round the WIP qty to full pallets so production, transport
        # and raw-material computations use the same baseline.
        pallet_q = self._pallet_qty(wip_sku, qty)

        # Production
        self._accum_prod(prod_acc, producer, wip_sku, pallet_q)

        # Route WIP from output buffer to target main storage
        if wip_sku.startswith("veg_"):
            self._accum_tx(tx_acc, out_node, target_ms, wip_sku, pallet_q)
        else:
            self._accum_tx(tx_acc, out_node, "WIP_storage", wip_sku, pallet_q)
            self._accum_tx(tx_acc, "WIP_storage", target_ms, wip_sku, pallet_q)

        # Raw materials — compute need from the pallet-rounded WIP qty
        if supplier is None:
            return
        bom_entry = prod_node.bom.get(wip_sku)
        if bom_entry is None:
            return
        for raw_sku, raw_qty_per in bom_entry["inputs"].items():
            raw_need = pallet_q * raw_qty_per
            self._accum_tx(tx_acc, supplier, lineside, raw_sku, raw_need)
            self._accum_tx(tx_acc, "source", supplier, raw_sku, raw_need)

    # ------------------------------------------------------------------
    # _execute_decision
    # ------------------------------------------------------------------

    def _execute_decision(self, decision: Decision) -> None:
        """Register transport orders on edges and production orders on nodes."""
        for order in decision.transport_orders:
            edge = self.find_edge(order.from_node, order.to_node)
            if edge is not None:
                edge.add_transport_order(order)
            else:
                self.log.append({
                    "time": self.env.now(),
                    "type": "transport_order_dropped",
                    "sku": order.sku,
                    "quantity": order.quantity,
                    "from": order.from_node,
                    "to": order.to_node,
                    "reason": "edge_removed_between_decision_and_execution",
                })
        for order in decision.production_orders:
            node = self._production_nodes.get(order.node_name)
            if node is not None:
                node.add_production_order(order)
            else:
                self.log.append({
                    "time": self.env.now(),
                    "type": "production_order_dropped",
                    "sku": order.sku,
                    "quantity": order.quantity,
                    "node": order.node_name,
                    "reason": "production_node_not_found",
                })
