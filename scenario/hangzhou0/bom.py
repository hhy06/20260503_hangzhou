"""Bill-of-materials definitions for the Hangzhou scenario.

Depends on ``sku.N`` for the number of FG SKUs.
"""

from scenario.hangzhou0.sku import N

# ---------------------------------------------------------------------------
# WIP Ingredient maps  (what raw materials go into each WIP SKU)
# ---------------------------------------------------------------------------

# sauce_i: smallpack_s_i + 2×meat_l + 2×oil_j + 2×vegetable_k
SAUCE_INGREDIENTS: dict[int, dict[str, int]] = {}
_sauce_meat = [1, 2, 3, 4, 1, 2, 3, 4, 1, 2]
_sauce_oil  = [1, 2, 3, 4, 2, 3, 4, 1, 3, 4]
_sauce_veg  = [1, 2, 3, 4, 3, 4, 1, 2, 3, 1]
for i in range(1, N + 1):
    idx = i - 1
    SAUCE_INGREDIENTS[i] = {
        f"smallpack_s_{i}": 1,
        f"meat_{_sauce_meat[idx]}": 2,
        f"oil_{_sauce_oil[idx]}": 2,
        f"vegetable_{_sauce_veg[idx]}": 2,
    }

# powder_i: smallpack_p_i + 1×original_powder_a + 1×original_powder_b + 1×original_powder_c
POWDER_INGREDIENTS: dict[int, dict[str, int]] = {}
_powder_picks = [
    (1, 2, 3), (2, 3, 4), (3, 4, 5), (4, 5, 1), (5, 1, 2),
    (1, 3, 5), (2, 4, 1), (3, 5, 2), (4, 1, 3), (5, 2, 4),
]
for i in range(1, N + 1):
    a, b, c = _powder_picks[i - 1]
    POWDER_INGREDIENTS[i] = {
        f"smallpack_p_{i}": 1,
        f"original_powder_{a}": 1,
        f"original_powder_{b}": 1,
        f"original_powder_{c}": 1,
    }

# veg_i: smallpack_v_i + 1×dry_veg_a + 1×dry_veg_b
VEG_INGREDIENTS: dict[int, dict[str, int]] = {}
_veg_picks = [
    (1, 2), (2, 3), (3, 4), (4, 1),
    (1, 3), (2, 4), (1, 4), (2, 3),
    (3, 1), (4, 2),
]
for i in range(1, N + 1):
    a, b = _veg_picks[i - 1]
    VEG_INGREDIENTS[i] = {
        f"smallpack_v_{i}": 1,
        f"dry_veg_{a}": 1,
        f"dry_veg_{b}": 1,
    }


# ---------------------------------------------------------------------------
# FG BOM helper
# ---------------------------------------------------------------------------

def sku_bom_inputs(i: int) -> dict[str, int]:
    """Return the input dict for SKU_i BOM (sauce_i + powder_i + veg_i + packaging)."""
    inputs = {f"sauce_{i}": 1, f"powder_{i}": 1, f"veg_{i}": 1}
    if i % 2 == 0:
        inputs["bow"] = 1
        inputs["cap"] = 1
    else:
        inputs["pack"] = 1
    return inputs


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
