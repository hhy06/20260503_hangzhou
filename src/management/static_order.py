"""Static-order management — issues pre-defined transport orders on schedule.

A :class:`StaticOrderManagement` holds a list of static ``TransportOrder``
objects.  On each decision cycle it scans its un-issued orders and inserts
those whose ``start_time <= current_time`` into the decision output.
"""

from typing import Any
import salabim as sim

from src.management.base import Management, Snapshot, Decision
from src.infrastructure.edge import Edge, TransportOrder


class StaticOrderManagement(Management):
    """Periodic decision-maker that issues static transport orders.

    Parameters
    ----------
    transport_orders : list[TransportOrder]
        Static transport orders to manage.
    edges : list[Edge]
        All edges in the simulation (used for route lookup).
    name : str, optional
        SALABIM component name.
    decision_interval : float
        Minutes between decision cycles (default 10.0).
    env : sim.Environment | None
    """

    def __init__(
        self,
        transport_orders: list[TransportOrder],
        edges: list[Edge],
        name: str = "Management",
        decision_interval: float = 10.0,
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self.transport_orders = list(transport_orders)
        self.edges = edges
        self._issued: set[int] = set()
        self.log: list[dict] = []

        super().__init__(
            name=name, decision_interval=decision_interval, env=env, **kwargs,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def find_edge(self, from_node_name: str, to_node_name: str) -> Edge | None:
        """Locate the edge whose endpoints match the given node names."""
        for e in self.edges:
            if (
                e.from_node.node_name == from_node_name
                and e.to_node.node_name == to_node_name
            ):
                return e
        return None

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
            if i in self._issued:
                continue
            if order.start_time <= time + 1e-9:
                decision.transport_orders.append(order)
                self._issued.add(i)
        return decision

    # ------------------------------------------------------------------
    # _execute_decision
    # ------------------------------------------------------------------

    def _execute_decision(self, decision: Decision) -> None:
        """Dispatch transport orders to the matching edges."""
        now = self.env.now()
        for order in decision.transport_orders:
            edge = self.find_edge(order.from_node, order.to_node)
            if edge is not None:
                edge.add_transport_order(order)
            else:
                self.log.append({
                    "time": now,
                    "type": "order_dropped",
                    "sku": order.sku,
                    "quantity": order.quantity,
                    "from": order.from_node,
                    "to": order.to_node,
                    "reason": "no matching edge found",
                })
