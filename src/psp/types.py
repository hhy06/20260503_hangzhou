from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Shift:
    index: int
    day: int
    type: Literal["day", "night"]
    start_time: int
    end_time: int


@dataclass
class LineAssignment:
    shift_index: int
    line_id: str
    sku: str
    quantity: int
    feasible: bool = True


@dataclass
class MaterialOrder:
    shift_index: int
    sku: str
    quantity: float
    target_warehouse: str


@dataclass
class InventoryEntry:
    shift_index: int
    warehouse: str
    sku: str
    quantity: int


@dataclass
class MaterialMovement:
    shift_index: int
    from_node: str
    to_node: str
    sku: str
    quantity: float
    movement_type: str


@dataclass
class PspPlan:
    shifts: list[Shift] = field(default_factory=list)
    fg_assignments: list[LineAssignment] = field(default_factory=list)
    wip_assignments: list[LineAssignment] = field(default_factory=list)
    material_orders: list[MaterialOrder] = field(default_factory=list)
    inventory_trace: list[InventoryEntry] = field(default_factory=list)
    shortages: dict[str, int] = field(default_factory=dict)
    shipment_delivered: dict[str, int] = field(default_factory=dict)
    daily_report: list[dict] = field(default_factory=list)
    init_fg_stock: int = 0
    movements: list[MaterialMovement] = field(default_factory=list)
