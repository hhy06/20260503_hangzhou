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
    destination: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InboundShipment:
    sku: str
    quantity: int
    source: Any = None
    destination: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _find_edge_for_destination(edges_out: list, destination: str) -> list:
    immediate_dests = [e.to_node.node_name for e in edges_out]
    if destination in immediate_dests:
        return [e for e in edges_out if e.to_node.node_name == destination]
    return edges_out


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
        if self.edges_out and shipment.destination and shipment.destination != self.node_name:
            self.add_outbound_order(OutboundOrder(
                sku=shipment.sku,
                quantity=shipment.quantity,
                priority=shipment.metadata.get("priority", 10),
                destination=shipment.destination,
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
            "destination": order.destination,
        })

    def _dispatch_for_destination(self, destination: str) -> list[tuple[str, int]]:
        orders = [o for o in self.output_queue if o.destination == destination]
        if not orders:
            return []

        plan = []
        remaining_pallets = self.dispatch_max_pallets
        sorted_orders = sorted(orders, key=lambda o: o.priority)

        for order in sorted_orders:
            if remaining_pallets <= 0:
                break
            sku = order.sku
            avail = self.inventory.get(sku, 0)
            if avail <= 0:
                continue
            order_pallets = self.pallets_for_quantity(sku, order.quantity)
            avail_pallets = self.pallets_for_quantity(sku, avail)
            usable = min(order_pallets, avail_pallets, remaining_pallets)
            if usable <= 0:
                continue
            dq = self.quantity_for_pallets(sku, usable)
            if dq > 0:
                plan.append((sku, dq))
                remaining_pallets -= usable

        if not plan:
            return []

        dispatched = []
        for sku, target_qty in plan:
            rem = target_qty
            for order in orders:
                taken = min(rem, order.quantity)
                order.quantity -= taken
                rem -= taken
                if rem <= 0:
                    break
            actual = target_qty - rem
            if actual > 0:
                self.inventory[sku] -= actual
                if self.inventory[sku] == 0:
                    del self.inventory[sku]
                dispatched.append((sku, actual))

        self.output_queue = [o for o in self.output_queue if o.quantity > 0]
        self.output_queue.sort(key=lambda o: o.priority)

        if dispatched:
            self.log.append({
                "time": self.env.now(),
                "type": "dispatched",
                "destination": destination,
                "items": dispatched,
            })
            target_edges = _find_edge_for_destination(self.edges_out, destination)
            for sku, qty in dispatched:
                for edge in target_edges:
                    shipment = InboundShipment(
                        sku=sku,
                        quantity=qty,
                        source=self,
                        destination=destination,
                        metadata={"priority": 10},
                    )
                    if edge.to_node.can_accept(sku, qty):
                        edge.to_node.receive(shipment)

        return dispatched

    def dispatch_step(self) -> list[tuple[str, int]]:
        if not self.output_queue or not self.edges_out:
            return []

        all_dispatched = []
        destinations = set()
        for order in self.output_queue:
            if order.destination is not None:
                destinations.add(order.destination)

        for dest in sorted(destinations):
            d = self._dispatch_for_destination(dest)
            all_dispatched.extend(d)

        return all_dispatched

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
            "destination": order.destination,
        })

    def dispatch_step(self) -> list[tuple[str, int]]:
        if not self.output_queue or not self.edges_out:
            return []

        all_dispatched = []
        destinations = set()
        for order in self.output_queue:
            if order.destination is not None:
                destinations.add(order.destination)

        for dest in sorted(destinations):
            orders = [o for o in self.output_queue if o.destination == dest]
            if not orders:
                continue

            plan = []
            remaining_pallets = self.dispatch_max_pallets
            sorted_orders = sorted(orders, key=lambda o: o.priority)

            for order in sorted_orders:
                if remaining_pallets <= 0:
                    break
                sku = order.sku
                op = self.pallets_for_quantity(sku, order.quantity)
                usable = min(op, remaining_pallets)
                if usable <= 0:
                    continue
                dq = self.quantity_for_pallets(sku, usable)
                if dq > 0:
                    plan.append((sku, dq))
                    remaining_pallets -= usable

            dispatched = []
            for sku, target_qty in plan:
                rem = target_qty
                for order in orders:
                    taken = min(rem, order.quantity)
                    order.quantity -= taken
                    rem -= taken
                    if rem <= 0:
                        break
                dispatched.append((sku, target_qty - rem))

            self.output_queue = [o for o in self.output_queue if o.quantity > 0]
            self.output_queue.sort(key=lambda o: o.priority)

            if dispatched:
                self.log.append({
                    "time": self.env.now(),
                    "type": "dispatched",
                    "destination": dest,
                    "items": dispatched,
                })
                for sku, qty in dispatched:
                    target_edges = _find_edge_for_destination(self.edges_out, dest)
                    for edge in target_edges:
                        shipment = InboundShipment(
                            sku=sku,
                            quantity=qty,
                            source=self,
                            destination=dest,
                        )
                        if edge.to_node.can_accept(sku, qty):
                            edge.to_node.receive(shipment)
                all_dispatched.extend(dispatched)

        return all_dispatched

    def add_edge_out(self, edge):
        self.edges_out.append(edge)

    def add_edge_in(self, edge):
        self.edges_in.append(edge)

    def process(self):
        while True:
            if self.output_queue:
                self.dispatch_step()
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
