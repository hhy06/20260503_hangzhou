"""Bill-of-materials definitions for the ss_hangzhou0b scenario.

BOM data is stored on each SKU object. This module provides helpers
for backward compatibility and line-SKU mapping.
"""

from .sku import N, SKUS


def _build_ingredients(sku_id: str) -> dict[str, int]:
    sku = SKUS.get(sku_id)
    if sku and sku.bom:
        return sku.bom
    return {}


def sku_bom_inputs(i: int) -> dict[str, int]:
    return SKUS[f"SKU_{i}"].bom


LINE_SKU_MAP: dict[int, list[int]] = {
    1: [1, 6], 2: [2, 7], 3: [3, 8], 4: [4, 9], 5: [5, 10],
    6: [1], 7: [2], 8: [3],
    9: [4], 10: [5], 11: [6], 12: [7], 13: [8], 14: [9], 15: [10],
    16: [1, 6],
}

_sku_line_count = {i: 0 for i in range(1, N + 1)}
for _lnum, _skus in LINE_SKU_MAP.items():
    for _s in _skus:
        _sku_line_count[_s] += 1
for _i in range(1, N + 1):
    assert _sku_line_count[_i] >= 2, f"SKU_{_i} only has {_sku_line_count[_i]} line(s)"

SAUCE_INGREDIENTS: dict[int, dict[str, int]] = {}
POWDER_INGREDIENTS: dict[int, dict[str, int]] = {}
VEG_INGREDIENTS: dict[int, dict[str, int]] = {}

for i in range(1, N + 1):
    SAUCE_INGREDIENTS[i] = _build_ingredients(f"sauce_{i}")
    POWDER_INGREDIENTS[i] = _build_ingredients(f"powder_{i}")
    VEG_INGREDIENTS[i] = _build_ingredients(f"veg_{i}")
