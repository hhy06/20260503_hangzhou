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
        self.edge_name = name or f"{node_name_from} -> {node_name_to}"
        super().__init__(name=self.edge_name, env=env, **kwargs)

        self.pending_queue: list[TransportOrder] = []
        self.activated_queue: list[TransportOrder] = []
        self.edge_stock: dict[str, int] = {}   # in-transit items (debited from A, not yet received by B)
        self.log: list[dict] = []

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
        2. Debit the full amount from ``from_node`` via ``debit_whole``.
        3. Load debited items into ``self.edge_stock`` (in-transit buffer).
        4. Drain ``edge_stock`` to ``to_node.receive()`` — one item per
            ``batch_transport_time`` in PER_PALLET mode, ``batch_pallets`` pallets per
            ``batch_transport_time`` in BATCH mode.
        """
        sku = order.sku
        items_per_pallet = self.from_node.conversion_factors[sku]
        num_pallets = math.ceil(order.quantity / items_per_pallet)
        desired_items = num_pallets * items_per_pallet  # round up to full pallets

        # -- 1. Debit source node inventory (all-or-nothing) ----------------
        if not self.from_node.debit_whole(sku, desired_items):
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

        actual_items = desired_items
        actual_pallets = num_pallets

        self.log.append({
            "time": self.env.now(),
            "type": "transport_started",
            "sku": sku,
            "quantity": actual_items,
            "from": order.from_node,
            "to": order.to_node,
            "pallets": actual_pallets,
        })

        # -- 2. Load into edge stock (in-transit buffer) --------------------
        self.edge_stock[sku] = self.edge_stock.get(sku, 0) + actual_items

        # -- 3. Incremental delivery from edge stock to B --------------------
        if self.transfer_mode == TransferMode.PER_PALLET:
            while self.edge_stock.get(sku, 0) > 0:
                yield self.hold(self.batch_transport_time)
                self.to_node.receive(sku, 1, source=self.from_node)
                self.edge_stock[sku] -= 1
        else:  # BATCH
            while self.edge_stock.get(sku, 0) > 0:
                stock = self.edge_stock[sku]
                pallets_this_batch = min(
                    self.batch_pallets,
                    math.ceil(stock / items_per_pallet),
                )
                deliver = min(pallets_this_batch * items_per_pallet, stock)
                yield self.hold(self.batch_transport_time)
                self.to_node.receive(sku, deliver, source=self.from_node)
                self.edge_stock[sku] -= deliver

        del self.edge_stock[sku]  # clean up zero-key

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
                # Scan from highest priority (earliest expect_time) and pick
                # the first order whose source has enough stock.
                executed = False
                for i in range(len(self.activated_queue)):
                    candidate = self.activated_queue[i]
                    items_per_pallet = self.from_node.conversion_factors[candidate.sku]
                    num_pallets = math.ceil(candidate.quantity / items_per_pallet)
                    desired_items = num_pallets * items_per_pallet
                    if self.from_node.available_qty(candidate.sku) >= desired_items:
                        self.activated_queue.pop(i)
                        yield from self._execute_order(candidate)
                        executed = True
                        break
                if not executed:
                    yield self.hold(1.0)
            else:
                yield self.hold(1.0)     # check again soon
