"""Safe-stock management — pull-based replenishment from stock-level triggers.

The decision cycle is inherited from :class:`Management`:

  1. ``gather_info()`` — snapshot current simulation state.
  2. ``make_decisions(time, info)`` — pure-function decision logic that returns
     a ``Decision`` containing transport and production orders.
  3. ``_execute_decision(decision)`` — pushes the planned orders onto edges
     and production nodes.
"""

from typing import Any
import salabim as sim

from src.management.base import Management, Decision, Snapshot
from src.infrastructure.edge import Edge, TransportOrder
from src.infrastructure.production_node import ProductionOrder


class SafeStockManagement(Management):
    """Pull-based replenishment manager driven by safe-stock thresholds.

    Parameters
    ----------
    safe_stock_config : list[dict]
        Each dict has keys ``{sku, safe_stock, replenish_qty, storage,
        replenish_from | produce_at | push_to}``.
    nodes : dict[str, Component]
    edges : list[Edge]
    demand_orders : list[dict], optional
    decision_interval : float
        Minutes between decision cycles (default 10.0).
    """

    def __init__(
        self,
        safe_stock_config: list[dict],
        nodes: dict[str, Any],
        edges: list[Edge],
        demand_orders: list[dict] | None = None,
        decision_interval: float = 10.0,
        name: str = "SafeStockManagement",
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self.safe_stock_config = list(safe_stock_config)
        self.demand_orders = list(demand_orders) if demand_orders else []
        self._issued_demand: set[int] = set()
        self._next_order_id_counter: int = 1
        self.log: list[dict] = []

        super().__init__(
            nodes=nodes, edges=edges,
            name=name, decision_interval=decision_interval, env=env, **kwargs,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _next_oid(self) -> int:
        self._next_order_id_counter += 1
        return self._next_order_id_counter

    # ------------------------------------------------------------------
    # make_decisions — pure-function order generation
    # ------------------------------------------------------------------

    def make_decisions(self, time: float, info: Snapshot) -> Decision:
        """Generate orders based on the snapshot.

        Parameters
        ----------
        time : float
            Current simulation time.
        info : Snapshot
            Gathered state snapshot.

        Returns
        -------
        Decision
            Transport and production orders to issue.
        """
        decision = Decision()

        # --- 1. Demand orders (FG consumption) ---
        for i, d in enumerate(self.demand_orders):
            if i in self._issued_demand:
                continue
            if d.get("start_time", 0) <= time + 1e-9:
                decision.transport_orders.append(TransportOrder(
                    order_id=self._next_oid(),
                    sku=d["sku"],
                    quantity=d["quantity"],
                    from_node=d.get("from_node", "fg_storage"),
                    to_node=d.get("to_node", "sink"),
                    start_time=time,
                    expect_time=time + self.decision_interval,
                ))
                self._issued_demand.add(i)

        # --- 2. Safe-stock replenishment ---
        for entry in self.safe_stock_config:
            sku = entry["sku"]
            storage = entry["storage"]
            storage_stock = info.storage_stock.get(storage, {}).get(sku, 0)

            if "push_to" in entry:
                # Push: fire when stock EXISTS (clear output buffers)
                if storage_stock > 0:
                    qty = min(entry["replenish_qty"], storage_stock)
                    decision.transport_orders.append(TransportOrder(
                        order_id=self._next_oid(),
                        sku=sku, quantity=qty,
                        from_node=storage, to_node=entry["push_to"],
                        start_time=time,
                        expect_time=time + self.decision_interval,
                    ))

            elif "produce_at" in entry:
                # Production: fire when storage is below safe_stock
                if storage_stock < entry["safe_stock"]:
                    prod_node_name = entry["produce_at"]
                    pqueue = info.production_queues.get(prod_node_name, [])
                    if not any(j.sku == sku for j in pqueue):
                        decision.production_orders.append(ProductionOrder(
                            order_id=self._next_oid(),
                            sku=sku,
                            quantity=entry["replenish_qty"],
                            activate_time=time,
                            expect_time=time + self.decision_interval,
                            node_name=prod_node_name,
                        ))

            elif "replenish_from" in entry:
                # Transport: fire when storage is below safe_stock AND
                # the source has enough stock to fulfil the order.
                if storage_stock < entry["safe_stock"]:
                    src = entry["replenish_from"]
                    if src in info.source_nodes:
                        src_available = float("inf")
                    else:
                        src_available = info.storage_stock.get(src, {}).get(sku, 0)
                    if src_available >= entry["replenish_qty"]:
                        decision.transport_orders.append(TransportOrder(
                            order_id=self._next_oid(),
                            sku=sku,
                            quantity=entry["replenish_qty"],
                            from_node=src, to_node=storage,
                            start_time=time,
                            expect_time=time + self.decision_interval,
                        ))

        return decision

    # ------------------------------------------------------------------
    # _execute_decision — push orders onto edges / production nodes
    # ------------------------------------------------------------------

    def _execute_decision(self, decision: Decision) -> None:
        """Register the planned orders with edges and production nodes.

        Raises
        ------
        RuntimeError
            If any planned order references an edge or production node that no
            longer exists — a serious runtime inconsistency.
        """
        now = self.env.now()
        for order in decision.production_orders:
            prod_node = self.nodes.get(order.node_name)
            if prod_node is not None and hasattr(prod_node, "add_production_order"):
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
                prod_node.add_production_order(order)
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
