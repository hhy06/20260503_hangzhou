"""Warehouse node component for SALABIM simulation."""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import salabim as sim

from src.component_logger import ComponentLogger


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


class NodeRole(Enum):
    SOURCE = "source"
    WAREHOUSE = "warehouse"
    SINK = "sink"


def _find_edge_for_destination(edges_out: list, destination: str) -> list:
    immediate_dests = [e.to_node.node_name for e in edges_out]
    if destination in immediate_dests:
        return [e for e in edges_out if e.to_node.node_name == destination]
    return edges_out


class WarehouseNode(sim.Component):
    def __init__(
        self,
        name: str,
        role: NodeRole,
        conversion_factors: dict[str, int],
        env: sim.Environment | None = None,
        max_pallets: int | None = None,
        dispatch_interval: float = 1.0,
        dispatch_max_pallets: int = 1,
        display_name: str | None = None,
        logger: ComponentLogger | None = None,
        **kwargs,
    ):
        self._node_name = name
        self.display_name = display_name or name
        super().__init__(name=name, env=env, **kwargs)
        self.role = role
        self.conversion_factors: dict[str, int] = dict(conversion_factors)
        self.dispatch_interval = dispatch_interval
        self.dispatch_max_pallets = dispatch_max_pallets
        self._logger = logger

        if role == NodeRole.WAREHOUSE:
            self.node_max_pallets = max_pallets
            self.inventory: dict[str, int] = {}
        else:
            self.node_max_pallets = float("inf")

        if role == NodeRole.SINK:
            self.received: dict[str, int] = {}

        self.output_queue: list[OutboundOrder] = []
        self.edges_out: list = []
        self.edges_in: list = []
        self.log: list[dict] = []

    @property
    def node_name(self) -> str:
        return self._node_name

    def __repr__(self) -> str:
        return self.display_name

    # --- conversion helpers ---

    def items_per_pallet(self, sku: str) -> int:
        return self.conversion_factors[sku]

    def pallets_for_quantity(self, sku: str, quantity: int) -> int:
        if quantity <= 0:
            return 0
        return math.ceil(quantity / self.conversion_factors[sku])

    def quantity_for_pallets(self, sku: str, pallets: int) -> int:
        return pallets * self.conversion_factors[sku]

    # --- capacity ---

    def current_pallets(self) -> int:
        if self.role != NodeRole.WAREHOUSE:
            return 0
        total = 0
        for sku, qty in self.inventory.items():
            if qty > 0:
                total += self.pallets_for_quantity(sku, qty)
        return total

    def available_pallets(self) -> int:
        if self.role != NodeRole.WAREHOUSE:
            return float("inf")
        return self.node_max_pallets - self.current_pallets()

    def can_accept(self, sku: str, quantity: int) -> bool:
        if self.role != NodeRole.WAREHOUSE:
            return True
        needed = self.pallets_for_quantity(sku, quantity)
        return self.current_pallets() + needed <= self.node_max_pallets

    def add_sku(self, sku: str, items_per_pallet: int):
        if sku in self.conversion_factors:
            raise ValueError(f"SKU {sku} already exists")
        self.conversion_factors[sku] = items_per_pallet

    # --- inbound ---

    def receive(self, shipment: InboundShipment) -> bool:
        if self.role == NodeRole.SOURCE:
            return True

        if self.role == NodeRole.SINK:
            current = self.received.get(shipment.sku, 0)
            self.received[shipment.sku] = current + shipment.quantity
            self.log.append({
                "time": self.env.now(),
                "type": "received",
                "sku": shipment.sku,
                "quantity": shipment.quantity,
                "source": shipment.source.display_name
                if hasattr(shipment.source, "display_name")
                else str(shipment.source),
            })
            return True

        # WAREHOUSE
        if not self.can_accept(shipment.sku, shipment.quantity):
            return False

        current = self.inventory.get(shipment.sku, 0)
        self.inventory[shipment.sku] = current + shipment.quantity
        self.log.append({
            "time": self.env.now(),
            "type": "received",
            "sku": shipment.sku,
            "quantity": shipment.quantity,
            "source": shipment.source.display_name
            if hasattr(shipment.source, "display_name")
            else str(shipment.source),
        })
        if self.edges_out and shipment.destination and shipment.destination != self.node_name:
            self.add_outbound_order(OutboundOrder(
                sku=shipment.sku,
                quantity=shipment.quantity,
                priority=shipment.metadata.get("priority", 10),
                destination=shipment.destination,
            ))
        return True

    # --- outbound ---

    def add_outbound_order(self, order: OutboundOrder):
        if self.role == NodeRole.SINK:
            return

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

            if self.role == NodeRole.WAREHOUSE:
                avail = self.inventory.get(sku, 0)
                if avail <= 0:
                    continue
            else:  # SOURCE: infinite supply
                avail = float("inf")

            # Ship exact quantity (not pallet-rounded), bounded by available
            # inventory and remaining pallet capacity (fractional pallets allowed).
            max_by_capacity = int(remaining_pallets * self.conversion_factors[sku])
            ship_qty = min(order.quantity, avail, max_by_capacity)
            if ship_qty <= 0:
                continue

            remaining_pallets -= ship_qty / self.conversion_factors[sku]
            plan.append((sku, ship_qty))

        if not plan:
            return []

        merged = {}
        for sku, qty in plan:
            merged[sku] = merged.get(sku, 0) + qty
        plan = list(merged.items())

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

            if self.role == NodeRole.WAREHOUSE:
                self.inventory[sku] -= actual
                if self.inventory[sku] == 0:
                    del self.inventory[sku]

            if actual > 0:
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

    def dispatch_step(self) -> list[dict[str, Any]]:
        if self.role == NodeRole.SINK:
            return []
        if not self.output_queue or not self.edges_out:
            return []

        all_dispatched: list[dict[str, Any]] = []
        destinations = set()
        for order in self.output_queue:
            if order.destination is not None:
                destinations.add(order.destination)

        for dest in sorted(destinations):
            items = self._dispatch_for_destination(dest)
            for sku, qty in items:
                if qty > 0:
                    all_dispatched.append({
                        "sku": sku,
                        "quantity": qty,
                        "destination": dest,
                    })

        return all_dispatched

    def add_edge_out(self, edge):
        self.edges_out.append(edge)

    def add_edge_in(self, edge):
        self.edges_in.append(edge)

    def process(self):
        if self.role == NodeRole.SINK:
            yield self.hold(999999)
            return

        while True:
            dispatched: list[dict[str, Any]] = []
            if self.output_queue:
                dispatched = self.dispatch_step()
            if self._logger is not None:
                self._logger.log_warehouse_activation(self, dispatched)
            yield self.hold(self.dispatch_interval)
