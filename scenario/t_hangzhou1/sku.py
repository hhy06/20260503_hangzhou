"""SKU definitions and pallet sizes for the Hangzhou scenario.

Everything in this file is derived from *N* (the number of FG SKUs).
The data is hard-coded here; it could be read from a CSV in future.
"""

N = 10  # Number of FG SKUs

# ---------------------------------------------------------------------------
# SKU master list (sku_name → display_name)
# ---------------------------------------------------------------------------

# Raw materials for sauce production
_raw_sauce = {f"smallpack_s_{i}": f"酱包小包{i}" for i in range(1, N + 1)}
_raw_sauce.update({f"meat_{l}": f"肉{l}" for l in range(1, 5)})
_raw_sauce.update({f"oil_{j}": f"油{j}" for j in range(1, 5)})
_raw_sauce.update({f"vegetable_{k}": f"蔬菜{k}" for k in range(1, 5)})

# Raw materials for powder production
_raw_powder = {f"smallpack_p_{i}": f"粉包小包{i}" for i in range(1, N + 1)}
_raw_powder.update({f"original_powder_{k}": f"原粉{k}" for k in range(1, 6)})

# Raw materials for veg production
_raw_veg = {f"smallpack_v_{i}": f"菜包小包{i}" for i in range(1, N + 1)}
_raw_veg.update({f"dry_veg_{k}": f"干菜{k}" for k in range(1, 5)})

# Packaging materials
_packaging = {
    "bow": "碗",
    "cap": "盖",
    "pack": "外包装",
}

# WIP SKUs
_wip = {}
for i in range(1, N + 1):
    _wip[f"sauce_{i}"] = f"酱包{i}"
    _wip[f"powder_{i}"] = f"粉包{i}"
    _wip[f"veg_{i}"] = f"菜包{i}"

# FG SKUs
_fg = {f"SKU_{i}": f"成品SKU{i}" for i in range(1, N + 1)}

SKUS: dict[str, str] = {}
SKUS.update(_raw_sauce)
SKUS.update(_raw_powder)
SKUS.update(_raw_veg)
SKUS.update(_packaging)
SKUS.update(_wip)
SKUS.update(_fg)

# ---------------------------------------------------------------------------
# Pallet sizes (items per pallet)
# ---------------------------------------------------------------------------
PALLET_SIZE: dict[str, int] = {}
for sku in _raw_sauce:
    PALLET_SIZE[sku] = 100
for sku in _raw_powder:
    PALLET_SIZE[sku] = 100
for sku in _raw_veg:
    PALLET_SIZE[sku] = 100
for sku in _packaging:
    PALLET_SIZE[sku] = 100
for sku in _wip:
    PALLET_SIZE[sku] = 100
for sku in _fg:
    PALLET_SIZE[sku] = 50
