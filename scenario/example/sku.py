"""SKU definitions for the simple linear example."""
from src.model.sku import SKU

N = 2  # Number of FG SKUs

_raw = {
    "raw_a": "Raw Material A",
    "raw_b": "Raw Material B",
}

_fg = {
    "fg_x": "Finished Good X",
    "fg_y": "Finished Good Y",
}

SKUS: dict[str, SKU] = {}
for sku, name in _raw.items():
    SKUS[sku] = SKU(id=sku, name=name, pallet_size=1)
for sku, name in _fg.items():
    SKUS[sku] = SKU(id=sku, name=name, pallet_size=1)