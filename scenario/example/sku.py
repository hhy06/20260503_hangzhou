"""SKU definitions for the simple linear example."""
N = 2  # Number of FG SKUs

_raw = {
    "raw_a": "Raw Material A",
    "raw_b": "Raw Material B",
}

_fg = {
    "fg_x": "Finished Good X",
    "fg_y": "Finished Good Y",
}

SKUS: dict[str, str] = {}
SKUS.update(_raw)
SKUS.update(_fg)

PALLET_SIZE: dict[str, int] = {}
for sku in _raw:
    PALLET_SIZE[sku] = 1
for sku in _fg:
    PALLET_SIZE[sku] = 1
