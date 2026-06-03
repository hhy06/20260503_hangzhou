"""SKU model with BOM and production time properties."""

import math


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
    pallet_size : int | None
        Items per pallet. Must be set from xlsx data; raises if missing.
    unit : str
        Unit of measure (e.g., "个", "kg", "箱"). Currently informational only.
    """

    def __init__(
        self,
        id: str,
        name: str = "",
        bom: dict | None = None,
        bom_speed: float = 0.0,
        pallet_size: int | None = None,
        unit: str = "",
    ):
        self.id = id
        self.name = name if name else id
        self.bom = bom if bom is not None else {}
        self.bom_speed = bom_speed
        self.pallet_size = pallet_size
        self.unit = unit

    def __repr__(self) -> str:
        return f"SKU({self.id}: {self.name}, bom_speed={self.bom_speed})"

    def calculate_pallet_num(self, qty: int) -> int:
        """Round up qty to next full pallet.

        Raises
        ------
        ValueError
            If pallet_size is not set (None) or invalid (<=0).
        """
        if self.pallet_size is None or self.pallet_size <= 0:
            raise ValueError(
                f"SKU {self.id} has no valid pallet_size (got {self.pallet_size})"
            )
        return math.ceil(qty / self.pallet_size)