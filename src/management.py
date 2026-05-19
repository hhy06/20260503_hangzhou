"""Management component — reads static orders and issues them at the right time.

A :class:`Management` instance is a ``salabim.Component`` that holds a
list of static transport (and eventually production) orders.  It wakes up
every ``decision_interval`` time units and calls :meth:`make_decision`,
which scans its un-issued orders and inserts those whose
``start_time <= current_time`` onto the correct edge via
``edge.add_transport_order()``.
"""

from typing import Any
import salabim as sim

from src.edge import Edge, TransportOrder


class Management(sim.Component):
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
        Minutes between ``make_decision()`` calls (default 10.0).
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
        self.decision_interval = decision_interval
        # Track which orders have been issued (by list index)
        self._issued: set[int] = set()
        self.log: list[dict] = []

        super().__init__(name=name, env=env, **kwargs)

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
    # decision logic (extension point for future dynamic decisions)
    # ------------------------------------------------------------------

    def make_decision(self) -> None:
        """Issue any pending orders whose ``start_time`` has been reached."""
        now = self.env.now()
        for i, order in enumerate(self.transport_orders):
            if i in self._issued:
                continue
            if order.start_time <= now + 1e-9:
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
                self._issued.add(i)

    # ------------------------------------------------------------------
    # SALABIM process
    # ------------------------------------------------------------------

    def process(self):
        """SALABIM coroutine: call ``make_decision()`` periodically."""
        while True:
            self.make_decision()
            yield self.hold(self.decision_interval)
