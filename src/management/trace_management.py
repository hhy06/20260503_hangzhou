"""Trace management — observes the simulation without taking any actions.

A :class:`TraceManagement` participates in the standard
``gather_info → make_decisions → _execute_decision`` cycle but its
``make_decisions`` always returns an empty ``Decision``.  This is useful
for observing system state (e.g. logging) without influencing it.
"""

from typing import Any
import salabim as sim

from src.management.base import Management, Snapshot, Decision
from src.infrastructure.edge import Edge
from src.infrastructure.warehouse_node import NodeRole, WarehouseNode


class TraceManagement(Management):
    """Observes the simulation without issuing orders.

    Parameters
    ----------
    nodes : dict[str, Component]
    edges : list[Edge]
    decision_interval : float
    name : str, optional
    env : sim.Environment | None
    """

    def __init__(
        self,
        nodes: dict[str, Any],
        edges: list[Edge],
        decision_interval: float = 10.0,
        name: str = "TraceManagement",
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self.nodes = dict(nodes)
        self.edges = list(edges)

        self._edge_map: dict[str, Edge] = {}
        for e in self.edges:
            key = f"{e.from_node.node_name}->{e.to_node.node_name}"
            self._edge_map[key] = e

        self._production_nodes: dict[str, Any] = {}
        for name, node in self.nodes.items():
            if hasattr(node, "production_queue"):
                self._production_nodes[name] = node

        super().__init__(
            name=name, decision_interval=decision_interval, env=env, **kwargs,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def find_edge(self, from_node_name: str, to_node_name: str) -> Edge | None:
        return self._edge_map.get(f"{from_node_name}->{to_node_name}")

    # ------------------------------------------------------------------
    # gather_info
    # ------------------------------------------------------------------

    def gather_info(self) -> Snapshot:
        """Collect a full snapshot of stock levels, edge queues, and production queues."""
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
    # make_decisions — intentionally empty
    # ------------------------------------------------------------------

    def make_decisions(self, time: float, info: Snapshot) -> Decision:
        """No-op — this manager observes only and never issues orders."""
        return Decision()

    # ------------------------------------------------------------------
    # _execute_decision — intentionally empty
    # ------------------------------------------------------------------

    def _execute_decision(self, decision: Decision) -> None:
        """No-op — this manager never issues orders."""
