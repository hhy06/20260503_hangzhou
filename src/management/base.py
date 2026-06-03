"""Base Management component — abstract periodic decision-maker.

Every management subclass follows the same decision cycle:

  1. ``gather_info()`` — snapshot current simulation state into a
     :class:`Snapshot`.
  2. ``make_decisions(time, info)`` — pure-function decision logic that
     returns a :class:`Decision` containing transport and production orders.
  3. ``_execute_decision(decision)`` — pushes the planned orders onto edges
     and production nodes.
"""

from dataclasses import dataclass, field
from typing import Any
import salabim as sim

from src.infrastructure.edge import TransportOrder
from src.infrastructure.production_node import ProductionOrder
from src.infrastructure.warehouse_node import WarehouseNode, NodeRole


# ---------------------------------------------------------------------------
# Data classes for the gather / decide interface
# ---------------------------------------------------------------------------


@dataclass
class Snapshot:
    """Immutable-ish view of simulation state at a point in time.

    Populated by :meth:`Management.gather_info`.
    """
    current_time: float
    # node_name -> {sku: available_qty}
    storage_stock: dict[str, dict[str, int]] = field(default_factory=dict)
    # node_names that have infinite supply (e.g. source)
    source_nodes: set[str] = field(default_factory=set)
    # edge_key (from->to) -> list of pending orders
    edge_pending: dict[str, list[TransportOrder]] = field(default_factory=dict)
    # edge_key -> list of activated orders
    edge_activated: dict[str, list[TransportOrder]] = field(default_factory=dict)
    # node_name -> list[ProductionOrder] in the production queue
    production_queues: dict[str, list[ProductionOrder]] = field(default_factory=dict)


@dataclass
class Decision:
    """Output of :meth:`Management.make_decisions`.

    The process loop passes these orders to :meth:`_execute_decision` which
    registers them with edges and production nodes.
    """
    transport_orders: list[TransportOrder] = field(default_factory=list)
    production_orders: list[ProductionOrder] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base management
# ---------------------------------------------------------------------------


class Management(sim.Component):
    """Base class for management decision-makers in the simulation.

    Subclasses must implement :meth:`make_decisions` and optionally override
    :meth:`gather_info` and :meth:`_execute_decision`.

    Parameters
    ----------
    decision_interval : float
        Minutes between decision cycles (default 10.0).
    name : str, optional
        SALABIM component name.
    env : sim.Environment | None
    """

    def __init__(
        self,
        nodes: dict,
        edges: list,
        decision_interval: float = 10.0,
        name: str = "Management",
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self.nodes = dict(nodes)
        self.edges = list(edges)
        self.decision_interval = decision_interval
        super().__init__(name=name, env=env, **kwargs)

        self._production_nodes: dict[str, Any] = {}
        for name, node in self.nodes.items():
            if hasattr(node, "production_queue"):
                self._production_nodes[name] = node

        self._edge_map: dict[str, Any] = {}
        for e in self.edges:
            key = f"{e.from_node.node_name}->{e.to_node.node_name}"
            self._edge_map[key] = e

        self._lineside_suppliers: dict[str, str] = {}
        lineside_nodes = {pnode.upstream_node.node_name for pnode in self._production_nodes.values()}
        for e in self.edges:
            if e.to_node.node_name in lineside_nodes:
                self._lineside_suppliers[e.to_node.node_name] = e.from_node.node_name

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def find_edge(self, from_node_name: str, to_node_name: str) -> Any | None:
        return self._edge_map.get(f"{from_node_name}->{to_node_name}")

    # ------------------------------------------------------------------
    # gather_info — snapshot current simulation state
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
    # make_decisions — pure-function order generation
    # ------------------------------------------------------------------

    def make_decisions(self, time: float, info: Snapshot) -> Decision:
        """Generate orders based on the snapshot.

        Subclasses must override this.

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
        raise NotImplementedError(
            f"{type(self).__name__} must implement make_decisions()"
        )

    # ------------------------------------------------------------------
    # _execute_decision — push orders onto edges / production nodes
    # ------------------------------------------------------------------

    def _execute_decision(self, decision: Decision) -> None:
        """Register the planned orders with edges and production nodes.

        Subclasses must override this — the base does not know how to
        dispatch orders without node/edge references.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _execute_decision()"
        )

    # ------------------------------------------------------------------
    # SALABIM process
    # ------------------------------------------------------------------

    def process(self):
        """Periodic decision loop: gather, decide, execute, then hold."""
        while True:
            now = self.env.now()
            info = self.gather_info()
            decision = self.make_decisions(now, info)
            self._execute_decision(decision)
            yield self.hold(self.decision_interval)
