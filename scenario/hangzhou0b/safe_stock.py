"""Safe-stock configuration for the Hangzhou scenario.

Each entry in ``SAFE_STOCK`` is a dict with:
    sku             — the material
    safe_stock      — minimum stock to maintain
    replenish_qty   — how much to order/produce when below safe_stock
    storage         — which node to check
    replenish_from  — transport source (source or another warehouse)
    produce_at      — production node (WIP / FG only)

Generated in part by ``generate_stock.py`` / ``generate_demand.py``.
"""

from src.infrastructure.edge import TransportOrder

SAFE_STOCK: list[dict] = []

# =========================================================================
# 1. RAW MATERIALS — from source to primary storage
# =========================================================================

_RAW_SRC = "source"
_RAW_RM = "raw_material_storage"
_RAW_MS1 = "main_storage_1"
_RAW_SAFE = 2000
_RAW_REPLENISH = 1000

# sauce raw materials -> raw_material_storage
for i in range(1, 11):
    SAFE_STOCK.append(dict(sku=f"smallpack_s_{i}", safe_stock=_RAW_SAFE,
                           replenish_qty=_RAW_REPLENISH,
                           storage=_RAW_RM, replenish_from=_RAW_SRC))
for i in range(1, 5):
    for sku in (f"meat_{i}", f"oil_{i}", f"vegetable_{i}"):
        SAFE_STOCK.append(dict(sku=sku, safe_stock=_RAW_SAFE,
                               replenish_qty=_RAW_REPLENISH,
                               storage=_RAW_RM, replenish_from=_RAW_SRC))

# powder raw materials -> raw_material_storage
for i in range(1, 11):
    SAFE_STOCK.append(dict(sku=f"smallpack_p_{i}", safe_stock=_RAW_SAFE,
                           replenish_qty=_RAW_REPLENISH,
                           storage=_RAW_RM, replenish_from=_RAW_SRC))
for i in range(1, 5):
    SAFE_STOCK.append(dict(sku=f"original_powder_{i}", safe_stock=_RAW_SAFE,
                           replenish_qty=_RAW_REPLENISH,
                           storage=_RAW_RM, replenish_from=_RAW_SRC))

# veg raw materials -> main_storage_1
for i in range(1, 11):
    SAFE_STOCK.append(dict(sku=f"smallpack_v_{i}", safe_stock=_RAW_SAFE,
                           replenish_qty=_RAW_REPLENISH,
                           storage=_RAW_MS1, replenish_from=_RAW_SRC))
for i in range(1, 5):
    SAFE_STOCK.append(dict(sku=f"dry_veg_{i}", safe_stock=_RAW_SAFE,
                           replenish_qty=_RAW_REPLENISH,
                           storage=_RAW_MS1, replenish_from=_RAW_SRC))

# packaging -> main_storage_1 & main_storage_2
for ms in ("main_storage_1", "main_storage_2"):
    for sku in ("bow", "cap", "pack"):
        SAFE_STOCK.append(dict(sku=sku, safe_stock=_RAW_SAFE,
                               replenish_qty=_RAW_REPLENISH,
                               storage=ms, replenish_from=_RAW_SRC))

# =========================================================================
# 2. RAW MATERIALS — from primary storage to lineside (for production)
# =========================================================================

# Lineside safe stock must cover at least one production batch's BOM requirement.
# WIP replenish_qty=400, max BOM qty_per=2 → max material per SKU = 2*400 = 800
_LS_SAFE = 1000
_LS_REPLENISH = 500

# Sauce lines
SAUCE_INGREDIENTS: dict[int, dict[str, int]] = {}
_sauce_meat = [1, 2, 3, 4, 1, 2, 3, 4, 1, 2]
_sauce_oil  = [1, 2, 3, 4, 2, 3, 4, 1, 3, 4]
_sauce_veg  = [1, 2, 3, 4, 3, 4, 1, 2, 3, 1]
for i in range(1, 11):
    idx = i - 1
    SAUCE_INGREDIENTS[i] = {
        f"smallpack_s_{i}": 1,
        f"meat_{_sauce_meat[idx]}": 2,
        f"oil_{_sauce_oil[idx]}": 2,
        f"vegetable_{_sauce_veg[idx]}": 2,
    }
for i in range(1, 11):
    lineside = f"lineside_sauce_{i}"
    for sku in SAUCE_INGREDIENTS[i]:
        SAFE_STOCK.append(dict(sku=sku, safe_stock=_LS_SAFE,
                               replenish_qty=_LS_REPLENISH,
                               storage=lineside, replenish_from=_RAW_RM))

# Powder lines
POWDER_INGREDIENTS: dict[int, dict[str, int]] = {}
_powder_picks = [
    (1, 2, 3), (2, 3, 4), (3, 4, 5), (4, 5, 1), (5, 1, 2),
    (1, 3, 5), (2, 4, 1), (3, 5, 2), (4, 1, 3), (5, 2, 4),
]
for i in range(1, 11):
    a, b, c = _powder_picks[i - 1]
    POWDER_INGREDIENTS[i] = {
        f"smallpack_p_{i}": 1,
        f"original_powder_{a}": 1,
        f"original_powder_{b}": 1,
        f"original_powder_{c}": 1,
    }
POWDER_LINE_SKU = {1: [1, 7], 2: [2, 8], 3: [3, 9], 4: [4, 10], 5: [5], 6: [6]}
for pl in range(1, 7):
    lineside = f"lineside_powder_{pl}"
    seen: set[str] = set()
    for pi in POWDER_LINE_SKU[pl]:
        for sku in POWDER_INGREDIENTS[pi]:
            if sku not in seen:
                seen.add(sku)
                SAFE_STOCK.append(dict(sku=sku, safe_stock=_LS_SAFE,
                                       replenish_qty=_LS_REPLENISH,
                                       storage=lineside, replenish_from=_RAW_RM))

# Veg line
VEG_INGREDIENTS: dict[int, dict[str, int]] = {}
_veg_picks = [
    (1, 2), (2, 3), (3, 4), (4, 1),
    (1, 3), (2, 4), (1, 4), (2, 3),
    (3, 1), (4, 2),
]
for i in range(1, 11):
    a, b = _veg_picks[i - 1]
    VEG_INGREDIENTS[i] = {f"smallpack_v_{i}": 1, f"dry_veg_{a}": 1, f"dry_veg_{b}": 1}
_veg_sku_set: set[str] = set()
for vi in range(1, 11):
    _veg_sku_set.update(VEG_INGREDIENTS[vi].keys())
for sku in sorted(_veg_sku_set):
    SAFE_STOCK.append(dict(sku=sku, safe_stock=_LS_SAFE,
                           replenish_qty=_LS_REPLENISH,
                           storage="lineside_veg", replenish_from=_RAW_MS1))

# =========================================================================
# 3. WIP PRODUCTION — trigger when WIP_storage / main_storage is low
# =========================================================================

_WIP_SAFE = 800
_WIP_REPLENISH = 400

# sauce
for i in range(1, 11):
    SAFE_STOCK.append(dict(sku=f"sauce_{i}", safe_stock=_WIP_SAFE,
                           replenish_qty=_WIP_REPLENISH,
                           storage="WIP_storage", produce_at=f"workstation_sauce_{i}"))
# powder
_powder_sku_to_line: dict[int, int] = {}
for pl, skus in POWDER_LINE_SKU.items():
    for pi in skus:
        _powder_sku_to_line[pi] = pl
for i in range(1, 11):
    pl = _powder_sku_to_line[i]
    SAFE_STOCK.append(dict(sku=f"powder_{i}", safe_stock=_WIP_SAFE,
                           replenish_qty=_WIP_REPLENISH,
                           storage="WIP_storage", produce_at=f"workstation_powder_{pl}"))
# veg
for i in range(1, 11):
    SAFE_STOCK.append(dict(sku=f"veg_{i}", safe_stock=_WIP_SAFE,
                           replenish_qty=_WIP_REPLENISH,
                           storage=_RAW_MS1, produce_at="workstation_veg"))

# =========================================================================
# 4. WIP TRANSPORT — move from WIP_storage to main_storage_i
# =========================================================================

_WIP_TRANSFER_SAFE = 500
_WIP_TRANSFER_QTY = 200

for ms in ("main_storage_1", "main_storage_2"):
    for i in range(1, 11):
        for sku in (f"sauce_{i}", f"powder_{i}"):
            SAFE_STOCK.append(dict(sku=sku, safe_stock=_WIP_TRANSFER_SAFE,
                                   replenish_qty=_WIP_TRANSFER_QTY,
                                   storage=ms, replenish_from="WIP_storage"))
    for i in range(1, 11):
        SAFE_STOCK.append(dict(sku=f"veg_{i}", safe_stock=_WIP_TRANSFER_SAFE,
                               replenish_qty=_WIP_TRANSFER_QTY,
                               storage=ms, replenish_from=_RAW_MS1))

# =========================================================================
# 5. OUTPUT BUFFER PUSH — clear production output buffers
# =========================================================================
#
# When production completes, stock sits in the output buffer node.
# These entries push it onward to the next storage node immediately,
# preventing back-pressure on the workstation.
# =========================================================================

_PUSH_QTY = 400

# Sauce: output_sauce_i → WIP_storage
for i in range(1, 11):
    SAFE_STOCK.append(dict(sku=f"sauce_{i}", safe_stock=1,
                           replenish_qty=_PUSH_QTY,
                           storage=f"output_sauce_{i}",
                           push_to="WIP_storage"))

# Powder: output_powder_pl → WIP_storage
for pl in range(1, 7):
    seen_powder: set[str] = set()
    for pi in POWDER_LINE_SKU[pl]:
        sku = f"powder_{pi}"
        if sku not in seen_powder:
            seen_powder.add(sku)
            SAFE_STOCK.append(dict(sku=sku, safe_stock=1,
                                   replenish_qty=_PUSH_QTY,
                                   storage=f"output_powder_{pl}",
                                   push_to="WIP_storage"))

# Veg: output_veg → main_storage_1
for i in range(1, 11):
    SAFE_STOCK.append(dict(sku=f"veg_{i}", safe_stock=1,
                           replenish_qty=_PUSH_QTY,
                           storage="output_veg",
                           push_to="main_storage_1"))

# =========================================================================
# 7. NOODLE LINESIDES — ingredients from main_storage to lineside_noodle_i
# =========================================================================

# Noodle lineside: FG replenish=100, 4 ingredients per SKU = 400 min needed
_LN_SAFE = 600
_LN_REPLENISH = 200

LINE_SKU_MAP: dict[int, list[int]] = {
    1: [1, 6], 2: [2, 7], 3: [3, 8], 4: [4, 9], 5: [5, 10],
    6: [1], 7: [2], 8: [3], 9: [4], 10: [5], 11: [6],
    12: [7], 13: [8], 14: [9], 15: [10], 16: [1, 6],
}


def sku_bom_inputs(i: int) -> dict[str, int]:
    inputs = {f"sauce_{i}": 1, f"powder_{i}": 1, f"veg_{i}": 1}
    if i % 2 == 0:
        inputs["bow"] = 1
        inputs["cap"] = 1
    else:
        inputs["pack"] = 1
    return inputs


for ln in range(1, 17):
    lineside = f"lineside_noodle_{ln}"
    ms = "main_storage_1" if ln <= 8 else "main_storage_2"
    needed: dict[str, int] = {}
    for sku_idx in LINE_SKU_MAP[ln]:
        inputs = sku_bom_inputs(sku_idx)
        for in_sku in inputs:
            needed[in_sku] = needed.get(in_sku, 1)
    for sku in needed:
        SAFE_STOCK.append(dict(sku=sku, safe_stock=_LN_SAFE,
                               replenish_qty=_LN_REPLENISH,
                               storage=lineside, replenish_from=ms))

# =========================================================================
# 8. FG PRODUCTION — trigger when fg_storage is low
# =========================================================================

_FG_SAFE = 200
_FG_REPLENISH = 100

_sku_to_line: dict[int, int] = {}
for ln, skus in LINE_SKU_MAP.items():
    for si in skus:
        if si not in _sku_to_line:
            _sku_to_line[si] = ln  # first line wins

for i in range(1, 11):
    ln = _sku_to_line[i]
    SAFE_STOCK.append(dict(sku=f"SKU_{i}", safe_stock=_FG_SAFE,
                           replenish_qty=_FG_REPLENISH,
                           storage="fg_storage", produce_at=f"workstation_noodle_{ln}"))

# =========================================================================
# 9. FG OUTPUT PUSH — clear noodle workstation output buffers
# =========================================================================
for i in range(1, 11):
    ln = _sku_to_line[i]
    SAFE_STOCK.append(dict(sku=f"SKU_{i}", safe_stock=1,
                           replenish_qty=_FG_REPLENISH,
                           storage=f"output_noodle_{ln}",
                           push_to="fg_storage"))

# =========================================================================
# 10. DEMAND ORDERS  —  daily FG consumption (fg_storage -> sink)
# =========================================================================

DAYS = 20
DEMAND_PER_DAY_PER_SKU = 50

DEMAND_ORDERS: list[dict] = []
for day in range(DAYS):
    t = day * 10
    for i in range(1, 11):
        DEMAND_ORDERS.append(dict(
            sku=f"SKU_{i}",
            quantity=DEMAND_PER_DAY_PER_SKU,
            from_node="fg_storage",
            to_node="sink",
            start_time=t + 0.5,
        ))
