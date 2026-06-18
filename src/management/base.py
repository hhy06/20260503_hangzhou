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

        # -- line -> supplier edges (multi-supplier support) ---------------
        # A lineside warehouse may receive from several pools
        # (e.g. raw_material_storage + soup_storage).  Keep the full list
        # of edges and let callers pick the right supplier for each SKU.
        lineside_nodes = {pnode.upstream_node.node_name for pnode in self._production_nodes.values()}
        self._lineside_supply_edges: dict[str, list[Edge]] = {}
        for e in self.edges:
            if e.to_node.node_name in lineside_nodes:
                self._lineside_supply_edges.setdefault(e.to_node.node_name, []).append(e)

        # Backward-compatible single-string alias (legacy scenarios) — kept
        # for trace_management.py / weigh_safe_stock_management.py lookups
        # that still use `.get(lineside)`.  Populated with the *first*
        # supplier per lineside.
        self._lineside_suppliers: dict[str, str] = {
            ls: edges[0].from_node.node_name
            for ls, edges in self._lineside_supply_edges.items()
        }

        # -- FG SKU detection ----------------------------------------------
        # A SKU is "finished goods" if at least one of its producers drains
        # output into fg_storage.  More robust than SKU-id-prefix heuristics.
        self._fg_skus: set[str] = set()
        for pnode in self._production_nodes.values():
            if pnode.downstream_node.node_name == "fg_storage":
                for sku in pnode.bom:
                    self._fg_skus.add(sku)

        # -- WIP pool mapping ----------------------------------------------
        # For every productive (non-FG) SKU, record which warehouse pool its
        # downstream node feeds.  Used by full-tree transport to choose the
        # right accumulation point for WIP output.
        # Keys: SKU IDs produced by any workstation; values: node name of the
        # pool warehouse (e.g. "soup_storage", "powder_wip_storage", ...).
        self._wip_pool: dict[str, str] = {}
        for pnode in self._production_nodes.values():
            out_node = pnode.downstream_node.node_name
            pool_name: str | None = None
            for e in self.edges:
                if e.from_node.node_name == out_node and e.to_node.node_name.endswith("_storage"):
                    pool_name = e.to_node.node_name
                    break
            if pool_name is None:
                continue
            for sku in pnode.bom:
                if sku in self._fg_skus:
                    continue
                self._wip_pool[sku] = pool_name

        # Legacy alias — retained for callers that still test membership.
        self._wip_in_central_storage: set[str] = set(self._wip_pool.keys())

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def find_edge(self, from_node_name: str, to_node_name: str) -> Any | None:
        return self._edge_map.get(f"{from_node_name}->{to_node_name}")

    def find_input_supplier(self, lineside: str, input_sku: str) -> str | None:
        """Pick the supply-node best suited to deliver *input_sku* to *lineside*.

        Returns the ``from_node`` name of one existing supply edge, or
        ``None`` if *lineside* has no supply edges.

        Resolution order:
          1. If *input_sku* is a WIP whose producer drains into a pool that
             is one of the lineside's suppliers, prefer that pool.
          2. Otherwise, prefer ``raw_material_storage`` if it is a supplier.
          3. Otherwise, prefer ``source`` (infinite supply) if it is a
             supplier.
          4. Otherwise, return the first supplier in the list.
        """
        edges = self._lineside_supply_edges.get(lineside, [])
        if not edges:
            return None
        supplier_names = [e.from_node.node_name for e in edges]

        wip_pool = self._wip_pool.get(input_sku)
        if wip_pool and wip_pool in supplier_names:
            return wip_pool

        if "raw_material_storage" in supplier_names:
            return "raw_material_storage"

        if "source" in supplier_names:
            return "source"

        return supplier_names[0]

    def transport_lead_time(self, from_node: str, to_node: str,
                            pad: float = 10.0) -> float:
        """Total lead time (minutes) to move material from *from_node* to
        *to_node*.

        Returns the edge's ``batch_transport_time`` plus a configurable
        *pad* (default 10 min) so that arrivals precede consumption time.
        Returns ``pad`` if the edge does not exist.
        """
        edge = self.find_edge(from_node, to_node)
        if edge is None:
            return pad
        return edge.batch_transport_time + pad

    def rounded_up_full_pallets_qty(self, node_name: str, sku: str, qty: int) -> int:
        """Get item quantity rounded up to next full pallet via node's sku_registry."""
        node = self.nodes.get(node_name)
        if node is None:
            raise ValueError(f"Node {node_name} not found")
        return node.rounded_up_full_pallets_qty(sku, qty)

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
