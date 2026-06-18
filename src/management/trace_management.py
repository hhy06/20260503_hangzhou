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
from src.infrastructure.warehouse_node import WarehouseNode


def _pallet_qty(sku_id: str, quantity: int, sku_registry: dict) -> int:
    """Round quantity up to next full pallet using SKU's pallet_size."""
    if quantity <= 0:
        return 0
    sku = sku_registry[sku_id]
    return sku.calculate_pallet_num(quantity)


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
        self._demand_orders = list(demand_orders or [])
        self._next_demand_idx = 0

        # sku -> [producer node names] derived from BOMs
        self._producers_of_sku: dict[str, list[str]] = {}

        # round-robin counters per SKU
        self._rr_counter: dict[str, int] = {}
        self._next_order_id: int = 1

        super().__init__(
            nodes=nodes, edges=edges,
            name=name, decision_interval=decision_interval, env=env, **kwargs,
        )

        # Build producers_of_sku after base sets up _production_nodes
        for n, pnode in self._production_nodes.items():
            for out_sku in pnode.bom:
                self._producers_of_sku.setdefault(out_sku, []).append(n)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

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
            raise ValueError(
                f"No edge from '{from_node}' to '{to_node}' for SKU {sku} "
                f"(qty {quantity}) — this is a topology/routing configuration bug."
            )
        pallet_rounded_qty = self.nodes[from_node].rounded_up_full_pallets_qty(sku, quantity)
        oid = self._next_order_id
        self._next_order_id += 1
        decision.transport_orders.append(TransportOrder(
            order_id=oid,
            sku=sku, quantity=pallet_rounded_qty,
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
        pallet_rounded_qty = self.nodes[node_name].rounded_up_full_pallets_qty(sku, quantity)
        oid = self._next_order_id
        self._next_order_id += 1
        decision.production_orders.append(ProductionOrder(
            order_id=oid,
            sku=sku, quantity=pallet_rounded_qty,
            activate_time=now, expect_time=now,
            node_name=node_name,
        ))

    # ------------------------------------------------------------------
    # gather_info — inherited from base (full stock/queue snapshot)
    # ------------------------------------------------------------------

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
        """Return the pallet-rounded transport quantity."""
        edge = self.find_edge(from_node, to_node)
        if edge is None:
            raise ValueError(
                f"No edge from '{from_node}' to '{to_node}' for SKU {sku} "
                f"(qty {qty}) — this is a topology/routing configuration bug."
            )
        return self.nodes[from_node].rounded_up_full_pallets_qty(sku, qty)

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

        # FG production
        self._accum_prod(prod_acc, noodle, fg_sku, qty)

        # Push FG from noodle output buffer to fg_storage
        self._accum_tx(
            tx_acc,
            noodle_node.downstream_node.node_name,
            "fg_storage", fg_sku, qty,
        )

        # For each BOM input of this FG SKU — pick supplier per input SKU
        bom = noodle_node.bom[fg_sku]
        for input_sku, qty_per in bom["inputs"].items():
            need = qty * qty_per
            supplier = self.find_input_supplier(lineside, input_sku)
            if supplier is None:
                continue

            # Transport: supplier -> lineside
            self._accum_tx(tx_acc, supplier, lineside, input_sku, need)

            if input_sku in self._producers_of_sku:
                self._accum_wip_tree(tx_acc, prod_acc, input_sku, need, supplier)
            else:
                # Raw material / packaging
                self._accum_tx(tx_acc, "source", supplier, input_sku, need)

    def _rounded_up_full_pallets_qty(self, node_name: str, sku: str, quantity: int) -> int:
        """Round *quantity* up to the next full pallet for *sku* at *node*."""
        return self.rounded_up_full_pallets_qty(node_name, sku, quantity)

    def _accum_wip_tree(
        self,
        tx_acc: dict[tuple[str, str, str], int],
        prod_acc: dict[tuple[str, str], int],
        wip_sku: str, qty: int, target_pool: str,
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

        # Round the WIP qty to full pallets so production, transport
        # and raw-material computations use the same baseline.
        pallet_rounded_q = self._rounded_up_full_pallets_qty(producer, wip_sku, qty)

        # Production
        self._accum_prod(prod_acc, producer, wip_sku, pallet_rounded_q)

        # Route WIP output: out_node -> producer's dedicated pool -> target_pool
        wip_pool = self._wip_pool.get(wip_sku)
        if wip_pool and wip_pool != target_pool:
            # Two-hop: producer output feeds its pool first, then flows to target
            self._accum_tx(tx_acc, out_node, wip_pool, wip_sku, pallet_rounded_q)
            self._accum_tx(tx_acc, wip_pool, target_pool, wip_sku, pallet_rounded_q)
        elif wip_pool:
            # Producer's pool *is* the target (or same node)
            self._accum_tx(tx_acc, out_node, target_pool, wip_sku, pallet_rounded_q)
        else:
            # No dedicated pool configured — deliver directly
            self._accum_tx(tx_acc, out_node, target_pool, wip_sku, pallet_rounded_q)

        # Raw materials — compute need from the pallet-rounded WIP qty
        raw_supplier = self.find_input_supplier(lineside, wip_sku)
        if raw_supplier is None:
            return
        bom_entry = prod_node.bom.get(wip_sku)
        if bom_entry is None:
            return
        for raw_sku, raw_qty_per in bom_entry["inputs"].items():
            raw_need = pallet_rounded_q * raw_qty_per
            raw_inp_supplier = self.find_input_supplier(lineside, raw_sku)
            if raw_inp_supplier is None:
                continue
            self._accum_tx(tx_acc, raw_inp_supplier, lineside, raw_sku, raw_need)
            self._accum_tx(tx_acc, "source", raw_inp_supplier, raw_sku, raw_need)

    # ------------------------------------------------------------------
    # _execute_decision
    # ------------------------------------------------------------------

    def _execute_decision(self, decision: Decision) -> None:
        """Register transport orders on edges and production orders on nodes.

        Raises
        ------
        RuntimeError
            If any planned order references an edge or production node that no
            longer exists — a serious runtime inconsistency.
        """
        for order in decision.transport_orders:
            edge = self.find_edge(order.from_node, order.to_node)
            if edge is not None:
                edge.add_transport_order(order)
            else:
                raise RuntimeError(
                    f"Transport order references missing edge: "
                    f"'{order.from_node}' -> '{order.to_node}' "
                    f"for SKU {order.sku} qty {order.quantity}. "
                    f"Edge was present during make_decisions but is now gone."
                )
        for order in decision.production_orders:
            node = self._production_nodes.get(order.node_name)
            if node is not None:
                node.add_production_order(order)
            else:
                raise RuntimeError(
                    f"Production order references missing node: "
                    f"'{order.node_name}' for SKU {order.sku} qty {order.quantity}. "
                    f"Node was present during make_decisions but is now gone."
                )
