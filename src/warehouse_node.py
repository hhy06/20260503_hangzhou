"""Warehouse node component for SALABIM simulation."""

import math
from dataclasses import dataclass, field
from typing import Any

import salabim as sim


@dataclass
class OutboundOrder:
    sku: str
    quantity: int
    priority: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InboundShipment:
    sku: str
    quantity: int
    source: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


class WarehouseNode(sim.Component):
    def __init__(
        self,
        name: str,
        max_pallets: int,
        conversion_factors: dict[str, int],
        env: sim.Environment | None = None,
        dispatch_interval: float = 1.0,
        dispatch_max_pallets: int = 1,
        **kwargs,
    ):
        self._node_name = name
        super().__init__(name=name, env=env, **kwargs)
        self.node_max_pallets = max_pallets
        self.conversion_factors: dict[str, int] = dict(conversion_factors)
        self.dispatch_interval = dispatch_interval
        self.dispatch_max_pallets = dispatch_max_pallets

        self.inventory: dict[str, int] = {}
        self.input_queue: list[InboundShipment] = []
        self.output_queue: list[OutboundOrder] = []

        self.edges_out: list = []
        self.edges_in: list = []

    @property
    def node_name(self) -> str:
        return self._node_name

    def items_per_pallet(self, sku: str) -> int:
        return self.conversion_factors[sku]

    def pallets_for_quantity(self, sku: str, quantity: int) -> int:
        if quantity <= 0:
            return 0
        return math.ceil(quantity / self.conversion_factors[sku])

    def quantity_for_pallets(self, sku: str, pallets: int) -> int:
        return pallets * self.conversion_factors[sku]

    def current_pallets(self) -> int:
        total = 0
        for sku, qty in self.inventory.items():
            if qty > 0:
                total += self.pallets_for_quantity(sku, qty)
        return total

    def available_pallets(self) -> int:
        return self.node_max_pallets - self.current_pallets()

    def can_accept(self, sku: str, quantity: int) -> bool:
        needed = self.pallets_for_quantity(sku, quantity)
        return self.current_pallets() + needed <= self.node_max_pallets

    def add_sku(self, sku: str, items_per_pallet: int):
        if sku in self.conversion_factors:
            raise ValueError(f"SKU {sku} already exists")
        self.conversion_factors[sku] = items_per_pallet

    def receive(self, shipment: InboundShipment) -> bool:
        if not self.can_accept(shipment.sku, shipment.quantity):
            return False

        current = self.inventory.get(shipment.sku, 0)
        self.inventory[shipment.sku] = current + shipment.quantity
        return True

    def receive_from_queue(self) -> bool:
        if not self.input_queue:
            return False

        shipment = self.input_queue[0]
        if self.receive(shipment):
            self.input_queue.pop(0)
            return True
        return False

    def add_outbound_order(self, order: OutboundOrder):
        self.output_queue.append(order)
        self.output_queue.sort(key=lambda o: o.priority)

    def compute_dispatch_plan(self, max_pallets: int) -> list[tuple[str, int]]:
        plan: list[tuple[str, int]] = []
        remaining_pallets = max_pallets

        sorted_orders = sorted(self.output_queue, key=lambda o: o.priority)

        for order in sorted_orders:
            if remaining_pallets <= 0:
                break

            sku = order.sku
            available_qty = self.inventory.get(sku, 0)
            if available_qty <= 0:
                continue

            order_pallets = self.pallets_for_quantity(sku, order.quantity)
            available_pallets = self.pallets_for_quantity(sku, available_qty)
            usable_pallets = min(order_pallets, available_pallets, remaining_pallets)

            if usable_pallets <= 0:
                continue

            dispatch_qty = self.quantity_for_pallets(sku, usable_pallets)
            if dispatch_qty > 0:
                plan.append((sku, dispatch_qty))
                remaining_pallets -= usable_pallets

        return plan

    def execute_dispatch(self, plan: list[tuple[str, int]]) -> list[tuple[str, int]]:
        dispatched = []
        for sku, qty in plan:
            actual = min(qty, self.inventory.get(sku, 0))
            if actual > 0:
                self.inventory[sku] -= actual
                if self.inventory[sku] == 0:
                    del self.inventory[sku]
                dispatched.append((sku, actual))

        to_remove = []
        for i, order in enumerate(self.output_queue):
            order_fulfilled = True
            for sku, qty in dispatched:
                if order.sku == sku:
                    order.quantity -= qty
                    if order.quantity > 0:
                        order_fulfilled = False
            if order_fulfilled and order.quantity <= 0:
                to_remove.append(i)

        for i in reversed(to_remove):
            self.output_queue.pop(i)

        self.output_queue.sort(key=lambda o: o.priority)
        return dispatched

    def dispatch_step(self) -> list[tuple[str, int]]:
        plan = self.compute_dispatch_plan(self.dispatch_max_pallets)
        if not plan:
            return []
        return self.execute_dispatch(plan)

    def add_edge_out(self, edge):
        self.edges_out.append(edge)

    def add_edge_in(self, edge):
        self.edges_in.append(edge)

    def process(self):
        while True:
            if self.output_queue:
                self.dispatch_step()
            yield self.hold(self.dispatch_interval)
