"""Safe-stock management — pull-based replenishment from stock-level triggers.

A :class:`SafeStockManagement` holds a ``SAFE_STOCK`` configuration mapping
each SKU to its target stock level, replenishment quantity, storage location,
and supply source (source node for raw materials, production node for WIP/FG).

On each decision cycle it:
  1. Issues any pending demand orders (FG consumption).
  2. Scans every SKU's current stock at its storage node; if below
     ``safe_stock``, it issues a transport order (raw material) or
     production order (WIP / FG) for the ``replenish_qty``.
"""

from typing import Any
import salabim as sim

from src.management.base import Management
from src.infrastructure.edge import Edge, TransportOrder
from src.infrastructure.production_node import ProductionOrder


class SafeStockManagement(Management):
    """Pull-based replenishment manager driven by safe-stock thresholds.

    Parameters
    ----------
    safe_stock_config : list[dict]
        Each dict has keys ``{sku, safe_stock, replenish_qty, storage,
        replenish_from | produce_at}``.  One entry per (SKU, storage) pair.
    nodes : dict[str, Component]
        All simulation nodes (used to look up storage & production nodes).
    edges : list[Edge]
        All simulation edges (used to issue transport orders).
    demand_orders : list[dict], optional
        Demand schedule: each entry has ``{sku, quantity, start_time}``.
        These are issued as ``fg_storage -> sink`` transport orders.
    decision_interval : float
        Minutes between decision cycles (default 10.0).
    name : str, optional
    env : sim.Environment | None
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
        self.nodes = dict(nodes)
        self.edges = list(edges)
        self.demand_orders = list(demand_orders) if demand_orders else []
        self._issued_demand: set[int] = set()
        self._job_id_counter: int = 0
        self.log: list[dict] = []

        super().__init__(
            name=name, decision_interval=decision_interval, env=env, **kwargs,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _next_job_id(self) -> int:
        self._job_id_counter += 1
        return self._job_id_counter

    def find_edge(self, from_node: str, to_node: str) -> Edge | None:
        for e in self.edges:
            if e.from_node.node_name == from_node and e.to_node.node_name == to_node:
                return e
        return None

    # ------------------------------------------------------------------
    # demand (FG consumption)
    # ------------------------------------------------------------------

    def _issue_demand(self) -> None:
        """Issue any demand orders whose start_time has been reached."""
        now = self.env.now()
        for i, d in enumerate(self.demand_orders):
            if i in self._issued_demand:
                continue
            if d.get("start_time", 0) <= now + 1e-9:
                edge = self.find_edge(d.get("from_node", "fg_storage"), d.get("to_node", "sink"))
                if edge is not None:
                    order = TransportOrder(
                        sku=d["sku"],
                        quantity=d["quantity"],
                        from_node=d.get("from_node", "fg_storage"),
                        to_node=d.get("to_node", "sink"),
                        start_time=now,
                        expect_time=now + self.decision_interval,
                    )
                    edge.add_transport_order(order)
                self._issued_demand.add(i)

    # ------------------------------------------------------------------
    # replenishment
    # ------------------------------------------------------------------

    def _replenish(self, sku: str, cfg: dict) -> None:
        """Issue a replenishment order for *sku* based on its config.

        Dispatch logic
        --------------
        * ``produce_at`` present      → production order (WIP / FG).
        * ``push_to`` present         → transport order **from** the storage
          node to ``push_to`` (moves output-buffer stock forward).
        * ``replenish_from`` present  → transport order **from** that node
          to storage, gated on source stock.
        """
        if "produce_at" in cfg:
            self._issue_production(sku, cfg)
        elif "push_to" in cfg:
            self._issue_push(sku, cfg)
        elif "replenish_from" in cfg:
            self._issue_transport(sku, cfg)

    def _issue_production(self, sku: str, cfg: dict) -> None:
        """Queue a production order — production retry handles material delays."""
        now = self.env.now()
        prod_node = self.nodes.get(cfg["produce_at"])
        if prod_node is not None and hasattr(prod_node, "add_production_order"):
            job_id = self._next_job_id()
            order = ProductionOrder(
                job_id=job_id,
                sku=sku,
                quantity=cfg["replenish_qty"],
                activate_time=now,
                expect_time=now + self.decision_interval,
                node_name=cfg["produce_at"],
            )
            prod_node.add_production_order(order)

    def _issue_transport(self, sku: str, cfg: dict) -> None:
        """Issue transport order, gated on source stock availability."""
        src_node = self.nodes.get(cfg["replenish_from"])
        if src_node is None:
            return

        # Gate: only issue if source has enough stock (SOURCE is infinite)
        available = src_node.available_qty(sku)
        if available < cfg["replenish_qty"]:
            return  # skip this cycle — will re-check next decision

        edge = self.find_edge(cfg["replenish_from"], cfg["storage"])
        if edge is not None:
            now = self.env.now()
            order = TransportOrder(
                sku=sku,
                quantity=cfg["replenish_qty"],
                from_node=cfg["replenish_from"],
                to_node=cfg["storage"],
                start_time=now,
                expect_time=now + self.decision_interval,
            )
            edge.add_transport_order(order)

    def _issue_push(self, sku: str, cfg: dict) -> None:
        """Push stock from the storage node forward to *push_to*.

        Unlike ``_issue_transport`` (which is a pull triggered by low stock
        at the destination), this is a push triggered by stock *existing*
        at the source — typically used to clear output buffers.
        """
        src_node = self.nodes.get(cfg["storage"])
        if src_node is None:
            return

        available = src_node.available_qty(sku)
        if available <= 0:
            return

        qty = min(cfg["replenish_qty"], available)
        edge = self.find_edge(cfg["storage"], cfg["push_to"])
        if edge is not None:
            now = self.env.now()
            order = TransportOrder(
                sku=sku,
                quantity=qty,
                from_node=cfg["storage"],
                to_node=cfg["push_to"],
                start_time=now,
                expect_time=now + self.decision_interval,
            )
            edge.add_transport_order(order)

    # ------------------------------------------------------------------
    # decision logic
    # ------------------------------------------------------------------

    def make_decision(self) -> None:
        """Check stock levels — issue replenishments for SKUs below safe stock."""
        # 1. Issue demand orders
        self._issue_demand()

        # 2. Check each entry's stock level
        for entry in self.safe_stock_config:
            storage_node = self.nodes.get(entry["storage"])
            if storage_node is None:
                continue
            available = storage_node.available_qty(entry["sku"])
            if "push_to" in entry:
                # Push entries fire when stock EXISTS (clear output buffers)
                if available > 0:
                    self._replenish(entry["sku"], entry)
            else:
                # Pull entries fire when stock is BELOW safe_stock
                if available < entry["safe_stock"]:
                    self._replenish(entry["sku"], entry)
