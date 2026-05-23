"""Warehouse node component for SALABIM simulation.

A ``WarehouseNode`` is a storage point in the logistics network.

Roles
-----
``SOURCE``
    Infinite supply — never holds inventory, never rejects.
``WAREHOUSE``
    Finite capacity (in pallets) — holds an ``inventory`` dict mapping
    SKU → item count.  Capacity is a **soft cap**: a warning is printed
    when pallet usage exceeds ``max_pallets``, but no goods are rejected.
``SINK``
    Endless consumption — accumulates received quantities in ``received``.

Inbound
-------
``receive(sku, quantity, source)`` — unconditionally adds stock with a
capacity warning if applicable.

Outbound
--------
Outbound is handled **by edges**, not by the warehouse itself.  An Edge's
``_execute_order`` debits the source node's inventory and delivers to the
destination node over time.  The warehouse no longer has a ``process``
dispatch loop.
"""

import math
from enum import Enum

import salabim as sim


class NodeRole(Enum):
    SOURCE = "source"
    WAREHOUSE = "warehouse"
    SINK = "sink"


class WarehouseNode(sim.Component):
    """A storage node in the logistics network.

    Parameters
    ----------
    name : str
        Internal node name (also used as SALABIM component name).
    role : NodeRole
    conversion_factors : dict[str, int]
        {sku: items_per_pallet} for pallet math.
    env : sim.Environment | None
    max_pallets : int | None
        Maximum pallet capacity (required for WAREHOUSE role, ignored for
        SOURCE/SINK).  This is a **soft cap** — exceeding it prints a
        warning instead of rejecting goods.
    display_name : str | None
        Human-readable label (falls back to *name*).
    """

    def __init__(
        self,
        name: str,
        role: NodeRole,
        conversion_factors: dict[str, int],
        env: sim.Environment | None = None,
        max_pallets: int | None = None,
        display_name: str | None = None,
        **kwargs,
    ):
        self._node_name = name
        self.display_name = display_name or name
        super().__init__(name=name, env=env, **kwargs)

        self.role = role
        self.conversion_factors: dict[str, int] = dict(conversion_factors)

        if role == NodeRole.WAREHOUSE:
            self.node_max_pallets = max_pallets
            self.inventory: dict[str, int] = {}
        else:
            self.node_max_pallets = float("inf")

        if role == NodeRole.SINK:
            self.received: dict[str, int] = {}

        self.edges_out: list = []
        self.edges_in: list = []
        self.log: list[dict] = []

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def node_name(self) -> str:
        return self._node_name

    def __repr__(self) -> str:
        return self.display_name

    # ------------------------------------------------------------------
    # conversion helpers
    # ------------------------------------------------------------------

    def items_per_pallet(self, sku: str) -> int:
        return self.conversion_factors.get(sku, 1)

    def pallets_for_quantity(self, sku: str, quantity: int) -> int:
        if quantity <= 0:
            return 0
        return math.ceil(quantity / self.conversion_factors.get(sku, 1))

    def quantity_for_pallets(self, sku: str, pallets: int) -> int:
        return pallets * self.conversion_factors.get(sku, 1)

    # ------------------------------------------------------------------
    # capacity (soft cap)
    # ------------------------------------------------------------------

    def current_pallets(self) -> int:
        """Total pallet slots currently occupied (WAREHOUSE only)."""
        if self.role != NodeRole.WAREHOUSE:
            return 0
        total = 0
        for sku, qty in self.inventory.items():
            if qty > 0:
                total += self.pallets_for_quantity(sku, qty)
        return total

    def available_pallets(self) -> int | float:
        """Remaining pallet capacity (``inf`` for non-WAREHOUSE)."""
        if self.role != NodeRole.WAREHOUSE:
            return float("inf")
        if self.node_max_pallets is None:
            return float("inf")
        return self.node_max_pallets - self.current_pallets()

    def check_capacity(self) -> None:
        """Log a warning if pallets exceed the soft cap."""
        if self.role == NodeRole.WAREHOUSE and self.node_max_pallets is not None:
            pal = self.current_pallets()
            if pal > self.node_max_pallets:
                self.log.append({
                    "time": self.env.now(),
                    "type": "capacity_warning",
                    "node": self.display_name,
                    "pallets": pal,
                    "max_pallets": self.node_max_pallets,
                })

    # ------------------------------------------------------------------
    # inventory query / mutation (the ONLY interface edges and production use)
    # ------------------------------------------------------------------

    def available_qty(self, sku: str) -> int | float:
        """Return current stock of *sku*.  SOURCE returns infinity."""
        if self.role == NodeRole.SOURCE:
            return float("inf")
        if self.role != NodeRole.WAREHOUSE:
            return 0
        return self.inventory.get(sku, 0)

    def debit_whole(self, sku: str, quantity: int) -> bool:
        """Deduct exactly *quantity* items.  Returns True on success.

        WAREHOUSE: fails (returns False) if stock < quantity — nothing is
        deducted.  SOURCE: always succeeds (infinite supply).
        """
        if self.role == NodeRole.SOURCE:
            return True
        if self.role != NodeRole.WAREHOUSE:
            return False
        current = self.inventory.get(sku, 0)
        if current < quantity:
            return False
        self.inventory[sku] = current - quantity
        if self.inventory[sku] <= 0:
            del self.inventory[sku]
        self.log.append({
            "time": self.env.now(),
            "type": "debited",
            "sku": sku,
            "quantity": quantity,
        })
        return True

    def add_sku(self, sku: str, items_per_pallet: int):
        """Register a new SKU with its pallet conversion factor."""
        if sku in self.conversion_factors:
            raise ValueError(f"SKU {sku} already exists")
        self.conversion_factors[sku] = items_per_pallet

    # ------------------------------------------------------------------
    # inbound
    # ------------------------------------------------------------------

    def receive(self, sku: str, quantity: int, source=None) -> None:
        """Accept inbound goods unconditionally.

        Parameters
        ----------
        sku : str
        quantity : int
        source : optional
            Source node (used for logging display name).
        """
        if self.role == NodeRole.SOURCE:
            return

        if self.role == NodeRole.SINK:
            self.received[sku] = self.received.get(sku, 0) + quantity
            self.log.append({
                "time": self.env.now(),
                "type": "received",
                "sku": sku,
                "quantity": quantity,
                "source": self._source_name(source),
            })
            return

        # WAREHOUSE
        self.inventory[sku] = self.inventory.get(sku, 0) + quantity
        self.log.append({
            "time": self.env.now(),
            "type": "received",
            "sku": sku,
            "quantity": quantity,
            "source": self._source_name(source),
        })
        self.check_capacity()

    @staticmethod
    def _source_name(source) -> str:
        if source is None:
            return "?"
        return (
            getattr(source, "display_name", None)
            or getattr(source, "node_name", None)
            or str(source)
        )

    # ------------------------------------------------------------------
    # edge registration
    # ------------------------------------------------------------------

    def add_edge_out(self, edge):
        self.edges_out.append(edge)

    def add_edge_in(self, edge):
        self.edges_in.append(edge)

    # ------------------------------------------------------------------
    # SALABIM process — periodic capacity check only
    # ------------------------------------------------------------------

    def process(self):
        """Periodically check capacity and print warnings."""
        while True:
            self.check_capacity()
            yield self.hold(10.0)
