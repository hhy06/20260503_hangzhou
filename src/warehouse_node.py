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
        self.output_queue: list[OutboundOrder] = []

        self.edges_out: list = []
        self.edges_in: list = []
        self.log: list[dict] = []

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
        self.log.append({
            "time": self.env.now(),
            "type": "received",
            "sku": shipment.sku,
            "quantity": shipment.quantity,
            "source": shipment.source.node_name if hasattr(shipment.source, 'node_name') else str(shipment.source),
        })
        if self.edges_out:
            self.add_outbound_order(OutboundOrder(
                sku=shipment.sku,
                quantity=shipment.quantity,
                priority=shipment.metadata.get("priority", 10),
            ))
        return True

    def add_outbound_order(self, order: OutboundOrder):
        self.output_queue.append(order)
        self.output_queue.sort(key=lambda o: o.priority)
        self.log.append({
            "time": self.env.now(),
            "type": "order_added",
            "sku": order.sku,
            "quantity": order.quantity,
            "priority": order.priority,
        })

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

        for order in self.output_queue:
            for sku, qty in dispatched:
                if order.sku == sku:
                    order.quantity -= qty
        self.output_queue = [o for o in self.output_queue if o.quantity > 0]
        self.output_queue.sort(key=lambda o: o.priority)
        return dispatched

    def dispatch_step(self) -> list[tuple[str, int]]:
        if not self.output_queue or not self.edges_out:
            return []
        plan = self.compute_dispatch_plan(self.dispatch_max_pallets)
        if not plan:
            return []
        dispatched = self.execute_dispatch(plan)
        if dispatched:
            self.log.append({
                "time": self.env.now(),
                "type": "dispatched",
                "items": dispatched,
            })
            for sku, qty in dispatched:
                for edge in self.edges_out:
                    shipment = InboundShipment(sku=sku, quantity=qty, source=self)
                    target = edge.to_node
                    if target.can_accept(sku, qty):
                        target.receive(shipment)
        return dispatched

    def add_edge_out(self, edge):
        self.edges_out.append(edge)

    def add_edge_in(self, edge):
        self.edges_in.append(edge)

    def process(self):
        while True:
            if self.output_queue:
                self.dispatch_step()
            yield self.hold(self.dispatch_interval)


class SourceNode(sim.Component):
    def __init__(
        self,
        name: str,
        conversion_factors: dict[str, int],
        env: sim.Environment | None = None,
        dispatch_interval: float = 1.0,
        dispatch_max_pallets: int = 999,
        **kwargs,
    ):
        self._node_name = name
        super().__init__(name=name, env=env, **kwargs)
        self.conversion_factors: dict[str, int] = dict(conversion_factors)
        self.dispatch_interval = dispatch_interval
        self.dispatch_max_pallets = dispatch_max_pallets
        self.output_queue: list[OutboundOrder] = []
        self.edges_out: list = []
        self.edges_in: list = []
        self.log: list[dict] = []

    @property
    def node_name(self) -> str:
        return self._node_name

    @property
    def node_max_pallets(self):
        return float("inf")

    def items_per_pallet(self, sku: str) -> int:
        return self.conversion_factors[sku]

    def pallets_for_quantity(self, sku: str, quantity: int) -> int:
        if quantity <= 0:
            return 0
        return math.ceil(quantity / self.conversion_factors[sku])

    def quantity_for_pallets(self, sku: str, pallets: int) -> int:
        return pallets * self.conversion_factors[sku]

    def can_accept(self, sku: str, quantity: int) -> bool:
        return True

    def receive(self, shipment: InboundShipment) -> bool:
        return True

    def add_outbound_order(self, order: OutboundOrder):
        self.output_queue.append(order)
        self.output_queue.sort(key=lambda o: o.priority)
        self.log.append({
            "time": self.env.now(),
            "type": "order_added",
            "sku": order.sku,
            "quantity": order.quantity,
            "priority": order.priority,
        })

    def dispatch_step(self) -> list[tuple[str, int]]:
        plan = []
        remaining_pallets = self.dispatch_max_pallets
        sorted_orders = sorted(self.output_queue, key=lambda o: o.priority)

        for order in sorted_orders:
            if remaining_pallets <= 0:
                break
            sku = order.sku
            order_pallets = self.pallets_for_quantity(sku, order.quantity)
            usable_pallets = min(order_pallets, remaining_pallets)
            if usable_pallets <= 0:
                continue
            dispatch_qty = self.quantity_for_pallets(sku, usable_pallets)
            if dispatch_qty > 0:
                plan.append((sku, dispatch_qty))
                remaining_pallets -= usable_pallets

        dispatched = []
        for sku, qty in plan:
            order.quantity -= qty
            dispatched.append((sku, qty))

        self.output_queue = [o for o in self.output_queue if o.quantity > 0]
        self.output_queue.sort(key=lambda o: o.priority)

        if dispatched:
            self.log.append({
                "time": self.env.now(),
                "type": "dispatched",
                "items": dispatched,
            })
        return dispatched

    def add_edge_out(self, edge):
        self.edges_out.append(edge)

    def add_edge_in(self, edge):
        self.edges_in.append(edge)

    def process(self):
        while True:
            if self.output_queue:
                dispatched = self.dispatch_step()
                if dispatched:
                    for sku, qty in dispatched:
                        for edge in self.edges_out:
                            shipment = InboundShipment(sku=sku, quantity=qty, source=self)
                            target = edge.to_node
                            if target.can_accept(sku, qty):
                                target.receive(shipment)
            yield self.hold(self.dispatch_interval)


class SinkNode(sim.Component):
    def __init__(
        self,
        name: str,
        conversion_factors: dict[str, int],
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self._node_name = name
        super().__init__(name=name, env=env, **kwargs)
        self.conversion_factors: dict[str, int] = dict(conversion_factors)
        self.edges_out: list = []
        self.edges_in: list = []
        self.log: list[dict] = []
        self.received: dict[str, int] = {}

    @property
    def node_name(self) -> str:
        return self._node_name

    @property
    def node_max_pallets(self):
        return float("inf")

    def items_per_pallet(self, sku: str) -> int:
        return self.conversion_factors[sku]

    def pallets_for_quantity(self, sku: str, quantity: int) -> int:
        if quantity <= 0:
            return 0
        return math.ceil(quantity / self.conversion_factors[sku])

    def quantity_for_pallets(self, sku: str, pallets: int) -> int:
        return pallets * self.conversion_factors[sku]

    def current_pallets(self) -> int:
        return 0

    def available_pallets(self) -> int:
        return float("inf")

    def can_accept(self, sku: str, quantity: int) -> bool:
        return True

    def receive(self, shipment: InboundShipment) -> bool:
        current = self.received.get(shipment.sku, 0)
        self.received[shipment.sku] = current + shipment.quantity
        self.log.append({
            "time": self.env.now(),
            "type": "received",
            "sku": shipment.sku,
            "quantity": shipment.quantity,
            "source": shipment.source.node_name if hasattr(shipment.source, 'node_name') else str(shipment.source),
        })
        return True

    def add_outbound_order(self, order: OutboundOrder):
        pass

    def add_edge_out(self, edge):
        self.edges_out.append(edge)

    def add_edge_in(self, edge):
        self.edges_in.append(edge)

    def process(self):
        while True:
            yield self.hold(999999)
