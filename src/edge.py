"""Edge class for connections between warehouse nodes, now a sim.Component.

An Edge manages transport between exactly two nodes.  Transport orders
(``TransportOrder``) are queued on the edge; the edge's simulation process
executes them one-at-a-time in ``expect_time`` priority order.
"""

import math
from dataclasses import dataclass
from enum import Enum

import salabim as sim


class TransferMode(Enum):
    PER_PALLET = "per_pallet"
    BATCH = "batch"


@dataclass
class TransportOrder:
    """A directive to move *quantity* items of *sku* from one node to another.

    The order becomes eligible for execution when simulation time reaches
    *start_time*.  Among eligible orders, the edge always picks the one
    with the earliest *expect_time* (used as priority).
    """
    sku: str
    quantity: int
    from_node: str            # node_name of source
    to_node: str              # node_name of destination
    start_time: float         # earliest allowed activation time
    expect_time: float        # earlier = higher priority


class Edge(sim.Component):
    """A directed connection between two WarehouseNodes.

    Parameters
    ----------
    from_node : WarehouseNode
    to_node : WarehouseNode
    transfer_mode : TransferMode
        ``PER_PALLET`` — one pallet every *transfer_time* minutes.
        ``BATCH`` — up to *batch_size* pallets every *transfer_time* minutes.
    transfer_time : float
        Minutes between pallet (PER_PALLET) or batch (BATCH) deliveries.
    batch_size : int, optional
        Number of pallets per batch (only meaningful in BATCH mode).
    env : sim.Environment | None
    """

    def __init__(
        self,
        from_node,
        to_node,
        transfer_mode: TransferMode,
        transfer_time: float,
        batch_size: int = 1,
        name: str | None = None,
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self.from_node = from_node
        self.to_node = to_node
        self.transfer_mode = transfer_mode
        self.transfer_time = transfer_time
        self.batch_size = batch_size

        if transfer_mode == TransferMode.BATCH and batch_size < 1:
            raise ValueError("batch_size must be >= 1 for batch mode")

        node_name_from = (
            getattr(from_node, "node_name", None)
            or getattr(from_node, "display_name", None)
            or getattr(from_node, "name", None)
            if from_node is not None else "?"
        )
        node_name_to = (
            getattr(to_node, "node_name", None)
            or getattr(to_node, "display_name", None)
            or getattr(to_node, "name", None)
            if to_node is not None else "?"
        )
        self.edge_name = name or f"{node_name_from} -> {node_name_to}"
        super().__init__(name=self.edge_name, env=env, **kwargs)

        self.pending_queue: list[TransportOrder] = []
        self.activated_queue: list[TransportOrder] = []
        self.log: list[dict] = []

    def __repr__(self) -> str:
        return (
            f"Edge({self.edge_name}, mode={self.transfer_mode.value}, "
            f"transfer_time={self.transfer_time}, batch_size={self.batch_size})"
        )

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def add_transport_order(self, order: TransportOrder) -> None:
        """Queue a transport order.

        If *order.start_time* has already passed the order goes directly
        into the activated queue; otherwise it waits in the pending queue
        until its start time is reached.
        """
        if order.start_time <= self.env.now() + 1e-9:
            self.activated_queue.append(order)
            self.activated_queue.sort(key=lambda o: o.expect_time)
        else:
            self.pending_queue.append(order)

        self.log.append({
            "time": self.env.now(),
            "type": "transport_order_added",
            "sku": order.sku,
            "quantity": order.quantity,
            "from": order.from_node,
            "to": order.to_node,
            "start_time": order.start_time,
            "expect_time": order.expect_time,
        })

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def _execute_order(self, order: TransportOrder):
        """Run a single transport order.

        Flow
        ----
        1. Compute pallet count (quantity → ceil to full pallets).
        2. Debit the full amount from ``from_node.inventory`` (skipped for
           SOURCE nodes which have infinite supply).
        3. Deliver pallets incrementally — one per ``transfer_time`` in
           PER_PALLET mode, ``batch_size`` per ``transfer_time`` in BATCH
           mode — to ``to_node.receive()``.
        """
        sku = order.sku
        items_per_pallet = self.from_node.conversion_factors[sku]
        num_pallets = math.ceil(order.quantity / items_per_pallet)
        desired_items = num_pallets * items_per_pallet  # round up to full pallets

        # -- 1. Debit source node inventory (only WAREHOUSE nodes) ----------
        if hasattr(self.from_node, "inventory") and self.from_node.inventory is not None:
            inv = self.from_node.inventory
            current = inv.get(sku, 0)
            debit_quantity = min(desired_items, current)
            inv[sku] = current - debit_quantity
            if inv[sku] <= 0:
                del inv[sku]
        else:
            # SOURCE / no-inventory nodes: unlimited supply
            debit_quantity = desired_items

        if debit_quantity <= 0:
            self.log.append({
                "time": self.env.now(),
                "type": "transport_order_skipped",
                "sku": sku,
                "quantity": desired_items,
                "from": order.from_node,
                "to": order.to_node,
                "reason": "insufficient inventory",
            })
            return

        # Deliver exactly what was debited (no re-rounding to pallets).
        # The pallet count is informational only.
        actual_items = debit_quantity
        actual_pallets = math.ceil(actual_items / items_per_pallet)

        self.log.append({
            "time": self.env.now(),
            "type": "transport_started",
            "sku": sku,
            "quantity": actual_items,
            "from": order.from_node,
            "to": order.to_node,
            "pallets": actual_pallets,
        })

        # -- 2. Incremental delivery ----------------------------------------
        remaining = actual_items
        if self.transfer_mode == TransferMode.PER_PALLET:
            while remaining > 0:
                deliver = min(items_per_pallet, remaining)
                yield self.hold(self.transfer_time)
                self.to_node.receive(sku, deliver, source=self.from_node)
                remaining -= deliver
        else:  # BATCH
            while remaining > 0:
                pallets_this_batch = min(
                    self.batch_size,
                    math.ceil(remaining / items_per_pallet),
                )
                deliver = min(
                    pallets_this_batch * items_per_pallet,
                    remaining,
                )
                yield self.hold(self.transfer_time)
                self.to_node.receive(sku, deliver, source=self.from_node)
                remaining -= deliver

        self.log.append({
            "time": self.env.now(),
            "type": "transport_completed",
            "sku": sku,
            "quantity": actual_items,
            "from": order.from_node,
            "to": order.to_node,
        })

    # ------------------------------------------------------------------
    # SALABIM process — transport execution loop
    # ------------------------------------------------------------------

    def process(self):
        """Pick eligible orders and execute them one-by-one."""
        while True:
            now = self.env.now()

            # Promote pending orders whose start time has arrived
            still_pending: list[TransportOrder] = []
            for order in self.pending_queue:
                if order.start_time <= now + 1e-9:
                    self.activated_queue.append(order)
                else:
                    still_pending.append(order)
            self.pending_queue = still_pending

            if self.activated_queue:
                self.activated_queue.sort(key=lambda o: o.expect_time)
                order = self.activated_queue.pop(0)
                yield from self._execute_order(order)
            else:
                yield self.hold(1.0)     # check again soon
