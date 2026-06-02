"""Bill-of-materials definitions for the Hangzhou scenario.

Depends on ``sku.N`` for the number of FG SKUs.

BOM data is now stored on each SKU object. This module provides helpers
for backward compatibility and line-SKU mapping.
"""

from .sku import N, SKUS

# ---------------------------------------------------------------------------
# Backward compatibility helpers (used by plant_topology.py)
# ---------------------------------------------------------------------------

def _build_ingredients(sku_id: str) -> dict[str, int]:
    """Return the ingredient dict for a WIP/FG SKU (builds from SKU.bom)."""
    sku = SKUS.get(sku_id)
    if sku and sku.bom:
        return sku.bom
    return {}


# ---------------------------------------------------------------------------
# FG BOM helper
# ---------------------------------------------------------------------------

def sku_bom_inputs(i: int) -> dict[str, int]:
    """Return the input dict for SKU_i BOM (alias to SKU.bom)."""
    return SKUS[f"SKU_{i}"].bom


# ---------------------------------------------------------------------------
# Noodle line → SKU assignment  (each FG SKU produced by >= 2 noodle lines)
# ---------------------------------------------------------------------------

LINE_SKU_MAP: dict[int, list[int]] = {
    1: [1, 6], 2: [2, 7], 3: [3, 8], 4: [4, 9], 5: [5, 10],
    6: [1], 7: [2], 8: [3],
    9: [4], 10: [5], 11: [6], 12: [7], 13: [8], 14: [9], 15: [10],
    16: [1, 6],
}

# Validation: every SKU must be assigned to at least 2 lines
_sku_line_count = {i: 0 for i in range(1, N + 1)}
for _lnum, _skus in LINE_SKU_MAP.items():
    for _s in _skus:
        _sku_line_count[_s] += 1
for _i in range(1, N + 1):
    assert _sku_line_count[_i] >= 2, f"SKU_{_i} only has {_sku_line_count[_i]} line(s)"


# ---------------------------------------------------------------------------
# Backward compatibility: SAUCE_INGREDIENTS, POWDER_INGREDIENTS, VEG_INGREDIENTS
# These are now derived from SKUS to support existing code.
# ---------------------------------------------------------------------------

SAUCE_INGREDIENTS: dict[int, dict[str, int]] = {}
POWDER_INGREDIENTS: dict[int, dict[str, int]] = {}
VEG_INGREDIENTS: dict[int, dict[str, int]] = {}

for i in range(1, N + 1):
    SAUCE_INGREDIENTS[i] = _build_ingredients(f"sauce_{i}")
    POWDER_INGREDIENTS[i] = _build_ingredients(f"powder_{i}")
    VEG_INGREDIENTS[i] = _build_ingredients(f"veg_{i}")
