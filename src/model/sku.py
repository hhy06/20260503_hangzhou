"""SKU model with BOM and production time properties."""

from dataclasses import dataclass, field


@dataclass
class SKU:
    """A stock-keeping unit with bill-of-materials and production time.

    Attributes
    ----------
    id : str
        Unique identifier (e.g., "SKU_1", "sauce_1", "flour").
    name : str
        Human-readable display name for logging/output.
    bom : dict[str, int]
        Bill-of-materials: {material_sku_id: amount_per_unit}.
        Empty dict for raw materials with no inputs.
    bom_speed : float
        Units produced per minute. Default 0 for raw materials.
        Each node can override this speed in its own BOM config.
    pallet_size : int
        Items per pallet.
    unit : str
        Unit of measure (e.g., "个", "kg", "箱"). Currently informational only.
    """
    id: str
    name: str = ""
    bom: dict[str, int] = field(default_factory=dict)
    bom_speed: float = 0.0
    pallet_size: int = 100
    unit: str = ""

    def __post_init__(self):
        if self.name == "":
            self.name = self.id

    def __repr__(self) -> str:
        return f"SKU({self.id}: {self.name}, bom_speed={self.bom_speed})"
