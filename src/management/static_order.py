"""Static-order management — issues pre-defined transport orders on schedule.

A :class:`StaticOrderManagement` holds a list of static ``TransportOrder``
objects.  On each decision cycle it scans its un-issued orders and inserts
those whose ``start_time <= current_time`` into the decision output.
"""

from typing import Any
import salabim as sim

from src.management.base import Management, Decision, Snapshot
from src.infrastructure.edge import Edge, TransportOrder
from src.infrastructure.production_node import ProductionOrder


class StaticOrderManagement(Management):
    """Periodic decision-maker that issues static transport orders.

    Parameters
    ----------
    transport_orders : list[TransportOrder]
        Static transport orders to manage.
    production_orders : list[ProductionOrder]
        Static production orders to manage.
    edges : list[Edge]
        All edges in the simulation (used for route lookup).
    nodes : dict[str, Any]
        All nodes in the simulation (used for production node lookup).
    name : str, optional
        SALABIM component name.
    decision_interval : float
        Minutes between decision cycles (default 10.0).
    env : sim.Environment | None
    """

    def __init__(
        self,
        transport_orders: list[TransportOrder],
        production_orders: list[ProductionOrder],
        edges: list[Edge],
        nodes: dict[str, Any],
        name: str = "Management",
        decision_interval: float = 10.0,
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self.transport_orders = list(transport_orders)
        self.production_orders = list(production_orders)
        self._issued_tx: set[int] = set()
        self._issued_prod: set[int] = set()
        self._next_order_id: int = 1
        self.log: list[dict] = []

        super().__init__(
            nodes=nodes, edges=edges,
            name=name, decision_interval=decision_interval, env=env, **kwargs,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # decision logic
    # ------------------------------------------------------------------

    def make_decisions(self, time: float, info: Snapshot) -> Decision:
        """Issue any pending orders whose ``start_time`` has been reached.

        The ``info`` snapshot is ignored — this manager reads from its
        pre-defined static order list.
        """
        decision = Decision()
        for i, order in enumerate(self.transport_orders):
            if i in self._issued_tx:
                continue
            if order.start_time <= time + 1e-9:
                issued = TransportOrder(
                    order_id=self._next_order_id,
                    sku=order.sku, quantity=order.quantity,
                    from_node=order.from_node, to_node=order.to_node,
                    start_time=order.start_time, expect_time=order.expect_time,
                )
                self._next_order_id += 1
                decision.transport_orders.append(issued)
                self._issued_tx.add(i)
        for i, order in enumerate(self.production_orders):
            if i in self._issued_prod:
                continue
            if order.activate_time <= time + 1e-9:
                issued = ProductionOrder(
                    order_id=self._next_order_id,
                    sku=order.sku, quantity=order.quantity,
                    activate_time=order.activate_time,
                    expect_time=order.expect_time,
                    node_name=order.node_name,
                    metadata=dict(order.metadata),
                )
                self._next_order_id += 1
                decision.production_orders.append(issued)
                self._issued_prod.add(i)
        return decision

    # ------------------------------------------------------------------
    # _execute_decision
    # ------------------------------------------------------------------

    def _execute_decision(self, decision: Decision) -> None:
        """Dispatch orders to edges / production nodes.

        Raises
        ------
        RuntimeError
            If any planned order references an edge or node that no longer exists.
        """
        now = self.env.now()
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
