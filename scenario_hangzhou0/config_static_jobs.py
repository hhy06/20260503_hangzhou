"""Static orders for the Hangzhou scenario.

Timeline (with fast transport edges, transfer_time=0.01):
  t=0       Source -> Primary storage (all raw materials)
  t=2       Storage -> Linesides (ingredients for WIP production)
  t=5       WIP production begins
              sauce: 10 parallel x 400u  -> done t=45
              powder: 6 lines, 1-2 SKUs  -> done t=85 (second wave)
              veg: 1 line, 10 SKUs x 400 -> done t=45 (speed=100)
  t=46      Phase 3a: output_sauce + output_powder(first wave) -> WIP_storage
  t=47      Phase 4a: output_veg -> main_storage_1
  t=48      Phase 4b: output_veg -> main_storage_2 (staggered, avoid race)
  t=90      Phase 3b: output_powder(second wave) -> WIP_storage
  t=92      Phase 5a: WIP_storage -> main_storage_1 (split: 200 of each)
  t=93      Phase 5b: WIP_storage -> main_storage_2 (staggered, avoid race)
  t=215     Phase 6: Main_storage -> Noodle linesides
  t=220     Noodle production begins (each SKU 100u @ speed=5 -> ~20min)
  t=300     Phase 7: Output_noodle_i -> fg_storage
  t=302     Phase 8: fg_storage -> sink
"""

from src.edge import TransportOrder
from src.production_node import ProductionOrder

from scenario_hangzhou0.config import (
    N, NUM_POWDER_LINES, NUM_NOODLE_LINES,
    SAUCE_INGREDIENTS, POWDER_INGREDIENTS, VEG_INGREDIENTS,
    LINE_SKU_MAP, sku_bom_inputs,
)

# Production quantities
# Each sauce/powder/veg produces enough for BOTH main storages (200 each)
SAUCE_QTY = 400   # 200 to main_storage_1 + 200 to main_storage_2
POWDER_QTY = 400  # 200 to main_storage_1 + 200 to main_storage_2
VEG_QTY = 400     # 200 to main_storage_1 + 200 to main_storage_2
SKU_QTY = 100     # per noodle line


def _orders_same_edge(from_node: str, to_node: str,
                       sku_qty_map: dict[str, int],
                       start_time: float, expect_time: float = 999) -> list[TransportOrder]:
    orders = []
    for sku, qty in sku_qty_map.items():
        orders.append(TransportOrder(
            sku=sku, quantity=qty,
            from_node=from_node, to_node=to_node,
            start_time=start_time, expect_time=expect_time,
        ))
    return orders


TRANSPORT_ORDERS: list[TransportOrder] = []

# ==============================
# Phase 1: Source -> Primary Storage  (t=0)
# ==============================

# Source -> raw_material_storage: all sauce raw materials
for i in range(1, N + 1):
    for sku, qty_per in SAUCE_INGREDIENTS[i].items():
        TRANSPORT_ORDERS.append(TransportOrder(
            sku=sku, quantity=qty_per * SAUCE_QTY,
            from_node="source", to_node="raw_material_storage",
            start_time=0, expect_time=10,
        ))

# Source -> raw_material_storage: all powder raw materials
for i in range(1, N + 1):
    for sku, qty_per in POWDER_INGREDIENTS[i].items():
        TRANSPORT_ORDERS.append(TransportOrder(
            sku=sku, quantity=qty_per * POWDER_QTY,
            from_node="source", to_node="raw_material_storage",
            start_time=0, expect_time=10,
        ))

# Source -> main_storage_1: all veg raw materials
for i in range(1, N + 1):
    for sku, qty_per in VEG_INGREDIENTS[i].items():
        TRANSPORT_ORDERS.append(TransportOrder(
            sku=sku, quantity=qty_per * VEG_QTY,
            from_node="source", to_node="main_storage_1",
            start_time=0, expect_time=10,
        ))

# Source -> main_storage_1 & main_storage_2: packaging
for ms in ("main_storage_1", "main_storage_2"):
    for pkg_sku, pkg_qty in [("bow", 800), ("cap", 800), ("pack", 800)]:
        TRANSPORT_ORDERS.append(TransportOrder(
            sku=pkg_sku, quantity=pkg_qty,
            from_node="source", to_node=ms,
            start_time=0, expect_time=10,
        ))

# ==============================
# Phase 2: Storage -> Linesides  (t=2)
# ==============================

# raw_material_storage -> lineside_sauce_i
for i in range(1, N + 1):
    sku_qty = {sku: qty * SAUCE_QTY for sku, qty in SAUCE_INGREDIENTS[i].items()}
    TRANSPORT_ORDERS.extend(_orders_same_edge(
        "raw_material_storage", f"lineside_sauce_{i}",
        sku_qty, start_time=2, expect_time=20,
    ))

# raw_material_storage -> lineside_powder_i
_powder_line_sku = {1: [1, 7], 2: [2, 8], 3: [3, 9], 4: [4, 10], 5: [5], 6: [6]}
for pl in range(1, NUM_POWDER_LINES + 1):
    sku_qty = {}
    for pi in _powder_line_sku[pl]:
        for sku, qty_per in POWDER_INGREDIENTS[pi].items():
            sku_qty[sku] = sku_qty.get(sku, 0) + qty_per * POWDER_QTY
    TRANSPORT_ORDERS.extend(_orders_same_edge(
        "raw_material_storage", f"lineside_powder_{pl}",
        sku_qty, start_time=2, expect_time=20,
    ))

# main_storage_1 -> lineside_veg
_veg_sku_qty = {}
for vi in range(1, N + 1):
    for sku, qty_per in VEG_INGREDIENTS[vi].items():
        _veg_sku_qty[sku] = _veg_sku_qty.get(sku, 0) + qty_per * VEG_QTY
TRANSPORT_ORDERS.extend(_orders_same_edge(
    "main_storage_1", "lineside_veg",
    _veg_sku_qty, start_time=2, expect_time=20,
))

# ==============================
# Phase 3: Output_buffers -> WIP_storage
# ==============================

# output_sauce_i -> WIP_storage (t=46, after all sauce production finishes at t=45)
for i in range(1, N + 1):
    TRANSPORT_ORDERS.append(TransportOrder(
        sku=f"sauce_{i}", quantity=SAUCE_QTY,
        from_node=f"output_sauce_{i}", to_node="WIP_storage",
        start_time=46, expect_time=50,
    ))

# output_powder_i -> WIP_storage
# Lines 1-4 produce 2 SKUs each (40min+40min=80min, finishes t=85)
# Lines 5-6 produce 1 SKU each (40min, finishes t=45)
# Wave 1 (t=46): single-SKU lines + first SKU of dual-SKU lines
# Wave 2 (t=90): second SKU of dual-SKU lines
for pl in range(1, NUM_POWDER_LINES + 1):
    for idx, pi in enumerate(_powder_line_sku[pl]):
        st = 46 if idx == 0 else 90  # first SKU at 46, second at 90
        TRANSPORT_ORDERS.append(TransportOrder(
            sku=f"powder_{pi}", quantity=POWDER_QTY,
            from_node=f"output_powder_{pl}", to_node="WIP_storage",
            start_time=st, expect_time=80,
        ))

# ==============================
# Phase 4: Veg output -> main_storage  (t=46, after veg finishes at t=45)
# Split evenly: each main storage gets half (200 of 400 produced)
# Stagger start times to prevent both edges racing for the same output_veg inventory
# ==============================
_MS_QTY_VEG = VEG_QTY // 2  # 200
_veg_stagger_t = {"main_storage_1": 46, "main_storage_2": 47}
for ms, st in _veg_stagger_t.items():
    for vi in range(1, N + 1):
        TRANSPORT_ORDERS.append(TransportOrder(
            sku=f"veg_{vi}", quantity=_MS_QTY_VEG,
            from_node="output_veg", to_node=ms,
            start_time=st, expect_time=250,
        ))

# ==============================
# Phase 5: WIP_storage -> main_storage  (t=92+, after powder wave 2 at t=90)
# Ship half the production to each main storage so both get equal share.
# Stagger start times (main_1 at t=92, main_2 at t=93) to prevent both edges
# racing for the same WIP_storage inventory.
# ==============================
_MS_QTY_SAUCE = SAUCE_QTY // 2   # 200
_MS_QTY_POWDER = POWDER_QTY // 2  # 200
_stagger_t = {"main_storage_1": 92, "main_storage_2": 93}
for ms, st in _stagger_t.items():
    for si in range(1, N + 1):
        TRANSPORT_ORDERS.append(TransportOrder(
            sku=f"sauce_{si}", quantity=_MS_QTY_SAUCE,
            from_node="WIP_storage", to_node=ms,
            start_time=st, expect_time=80,
        ))
    for pi in range(1, N + 1):
        TRANSPORT_ORDERS.append(TransportOrder(
            sku=f"powder_{pi}", quantity=_MS_QTY_POWDER,
            from_node="WIP_storage", to_node=ms,
            start_time=st, expect_time=80,
        ))

# ==============================
# Phase 6: Main_storage -> Noodle linesides  (t=215)
# ==============================
for ln in range(1, NUM_NOODLE_LINES + 1):
    ms = "main_storage_1" if ln <= 8 else "main_storage_2"
    lineside = f"lineside_noodle_{ln}"
    needed: dict[str, int] = {}
    for sku_idx in LINE_SKU_MAP[ln]:
        inputs = sku_bom_inputs(sku_idx)
        for in_sku, qty_per in inputs.items():
            needed[in_sku] = needed.get(in_sku, 0) + qty_per * SKU_QTY

    TRANSPORT_ORDERS.extend(_orders_same_edge(
        ms, lineside, needed, start_time=215, expect_time=260,
    ))

# ==============================
# Phase 7: Noodle outputs -> fg_storage  (t=300)
# ==============================
for ln in range(1, NUM_NOODLE_LINES + 1):
    output_node = f"output_noodle_{ln}"
    for sku_idx in LINE_SKU_MAP[ln]:
        sku_name = f"SKU_{sku_idx}"
        TRANSPORT_ORDERS.append(TransportOrder(
            sku=sku_name, quantity=SKU_QTY,
            from_node=output_node, to_node="fg_storage",
            start_time=300, expect_time=350,
        ))

# ==============================
# Phase 8: fg_storage -> sink  (t=302)
# ==============================
for si in range(1, N + 1):
    TRANSPORT_ORDERS.append(TransportOrder(
        sku=f"SKU_{si}", quantity=SKU_QTY,
        from_node="fg_storage", to_node="sink",
        start_time=302, expect_time=400,
    ))


# =========================================================================
# PRODUCTION JOBS
# =========================================================================

PRODUCTION_JOBS: list[ProductionOrder] = []
_job_id = 0

# Sauce production (t=5) - all 10 lines in parallel
for i in range(1, N + 1):
    _job_id += 1
    PRODUCTION_JOBS.append(ProductionOrder(
        job_id=_job_id, sku=f"sauce_{i}", quantity=SAUCE_QTY,
        activate_time=5, expect_time=30, node_name=f"workstation_sauce_{i}",
    ))

# Powder production (t=5) - 6 parallel lines
for pl in range(1, NUM_POWDER_LINES + 1):
    for pi in _powder_line_sku[pl]:
        _job_id += 1
        PRODUCTION_JOBS.append(ProductionOrder(
            job_id=_job_id, sku=f"powder_{pi}", quantity=POWDER_QTY,
            activate_time=5, expect_time=30,
            node_name=f"workstation_powder_{pl}",
        ))

# Veg production (t=5, serial - single workstation)
for vi in range(1, N + 1):
    _job_id += 1
    PRODUCTION_JOBS.append(ProductionOrder(
        job_id=_job_id, sku=f"veg_{vi}", quantity=VEG_QTY,
        activate_time=5, expect_time=210,
        node_name="workstation_veg",
    ))

# Noodle production (t=220, after all WIPs in linesides)
for ln in range(1, NUM_NOODLE_LINES + 1):
    for sku_idx in LINE_SKU_MAP[ln]:
        sku_name = f"SKU_{sku_idx}"
        _job_id += 1
        PRODUCTION_JOBS.append(ProductionOrder(
            job_id=_job_id, sku=sku_name, quantity=SKU_QTY,
            activate_time=220, expect_time=300,
            node_name=f"workstation_noodle_{ln}",
        ))
