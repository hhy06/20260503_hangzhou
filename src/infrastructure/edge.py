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
    order_id: int = 0         # unified identity (assigned by management at issue time)


class Edge(sim.Component):
    """A directed connection between two WarehouseNodes.

    Parameters
    ----------
    from_node : WarehouseNode
    to_node : WarehouseNode
    transfer_mode : TransferMode
        ``PER_PALLET`` — one pallet every *batch_transport_time* minutes.
        ``BATCH`` — up to *batch_pallets* pallets every *batch_transport_time* minutes.
    batch_transport_time : float
        Minutes between pallet (PER_PALLET) or batch (BATCH) deliveries.
    batch_pallets : int, optional
        Number of pallets per batch (only meaningful in BATCH mode).
    env : sim.Environment | None
    """

    def __init__(
        self,
        from_node,
        to_node,
        transfer_mode: TransferMode,
        batch_transport_time: float,
        batch_pallets: int = 1,
        name: str | None = None,
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self.from_node = from_node
        self.to_node = to_node
        self.transfer_mode = transfer_mode
        self.batch_transport_time = batch_transport_time
        self.batch_pallets = batch_pallets

        if transfer_mode == TransferMode.BATCH and batch_pallets < 1:
            raise ValueError("batch_pallets must be >= 1 for batch mode")

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
        self.edge_name = name or f"E({node_name_from} -> {node_name_to})"
        super().__init__(name=self.edge_name, env=env, **kwargs)

        self.pending_queue: list[TransportOrder] = []
        self.activated_queue: list[TransportOrder] = []
        self.edge_stock: dict[str, int] = {}   # in-transit items (debited from A, not yet received by B)
        self.log: list[dict] = []

    def __str__(self) -> str:
        return self.edge_name

    def __repr__(self) -> str:
        mode = self.transfer_mode.value
        return (
            f"Edge({self.from_node}->{self.to_node}, "
            f"mode={mode}, "
            f"batch_transport_time={self.batch_transport_time}, "
            f"batch_pallets={self.batch_pallets})"
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

        num_pallets = self.from_node.calculate_pallet_count(order.sku, order.quantity)

        self.log.append({
            "time": self.env.now(),
            "type": "transport_order_added",
            "subject": self.edge_name,
            "order_id": order.order_id,
            "sku": order.sku,
            "quantity": order.quantity,
            "pallets": num_pallets,
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
        1. Debit exactly *order.quantity* items from ``from_node`` via
           ``debit_whole``.  No pallet rounding — the quantity is the
           precise item count demanded.
        2. Load debited items into ``self.edge_stock`` (in-transit buffer).
        3. Drain ``edge_stock`` to ``to_node.receive()`` in pallet-sized
           trips: ``ceil(quantity / items_per_pallet)`` trips, each trip
           takes ``batch_transport_time``.  The last trip carries
           ``quantity % items_per_pallet`` items if there is a remainder.
        """
        sku = order.sku
        quantity = order.quantity
        items_per_pallet = self.from_node.items_per_pallet(sku)
        pallet_trips = math.ceil(quantity / items_per_pallet)

        # -- 1. Debit source node inventory (exact quantity, all-or-nothing) --
        if not self.from_node.debit_whole(sku, quantity):
            self.log.append({
                "time": self.env.now(),
                "type": "transport_order_skipped",
                "subject": self.edge_name,
                "order_id": order.order_id,
                "sku": sku,
                "quantity": quantity,
                "from": order.from_node,
                "to": order.to_node,
                "reason": "insufficient inventory",
            })
            order.start_time = self.env.now() + 1.0
            self.activated_queue.append(order)
            self.activated_queue.sort(key=lambda o: o.expect_time)
            return

        self.log.append({
            "time": self.env.now(),
            "type": "transport_started",
            "subject": self.edge_name,
            "order_id": order.order_id,
            "sku": sku,
            "quantity": quantity,
            "from": order.from_node,
            "to": order.to_node,
            "pallets": pallet_trips,
            "edge_stock_after": self.edge_stock.get(sku, 0),
        })

        # -- 2. Load into edge stock (in-transit buffer) --------------------
        self.edge_stock[sku] = self.edge_stock.get(sku, 0) + quantity

        # -- 3. Incremental delivery from edge stock to B --------------------
        if self.transfer_mode == TransferMode.PER_PALLET:
            remaining = self.edge_stock[sku]
            full_trips = remaining // items_per_pallet
            remainder = remaining % items_per_pallet
            for _ in range(full_trips):
                yield self.hold(self.batch_transport_time)
                self.to_node.receive(sku, items_per_pallet, source=self.from_node)
                remaining -= items_per_pallet
            if remainder > 0:
                yield self.hold(self.batch_transport_time)
                self.to_node.receive(sku, remainder, source=self.from_node)
                remaining -= remainder
        else:  # BATCH
            remaining = self.edge_stock[sku]
            full_pallets = remaining // items_per_pallet
            remainder_qty = remaining % items_per_pallet
            while full_pallets > 0 or remainder_qty > 0:
                pallets_this_batch = min(
                    self.batch_pallets,
                    full_pallets + (1 if remainder_qty > 0 else 0),
                )
                deliver_qty = min(pallets_this_batch * items_per_pallet, remaining)
                yield self.hold(self.batch_transport_time)
                self.to_node.receive(sku, deliver_qty, source=self.from_node)
                remaining -= deliver_qty
                full_pallets = remaining // items_per_pallet
                remainder_qty = remaining % items_per_pallet

        if sku in self.edge_stock:
            del self.edge_stock[sku]

        self.log.append({
            "time": self.env.now(),
            "type": "transport_completed",
            "subject": self.edge_name,
            "order_id": order.order_id,
            "sku": sku,
            "quantity": quantity,
            "from": order.from_node,
            "to": order.to_node,
            "edge_stock_after": 0,
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
                # Scan from highest priority (earliest expect_time) and pick
                # the first order whose source has enough stock.
                executed = False
                for i in range(len(self.activated_queue)):
                    candidate = self.activated_queue[i]
                    if self.from_node.available_qty(candidate.sku) >= candidate.quantity:
                        self.activated_queue.pop(i)
                        yield from self._execute_order(candidate)
                        executed = True
                        break
                if not executed:
                    yield self.hold(1.0)
            else:
                yield self.hold(1.0)     # check again soon
