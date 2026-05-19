"""Simulation configuration for Hangzhou scenario.

Flow (hangzhou):
  source
    -> raw_material_storage
      -> lineside_sauce_i  (i=1..10)
        -> workstation_sauce_i -> output_sauce_i -> WIP_storage
      -> lineside_powder_i  (i=1..6)
        -> workstation_powder_i -> output_powder_i -> WIP_storage
    -> main_storage_1
      -> lineside_noodle_i  (i=1..8)
        -> workstation_noodle_i -> output_noodle_i -> fg_storage
      -> lineside_veg
        -> workstation_veg -> output_veg -> main_storage_1, main_storage_2
    -> main_storage_2
      -> lineside_noodle_j  (j=9..16)
        -> workstation_noodle_j -> output_noodle_j -> fg_storage
    -> fg_storage -> sink

  source sends:
    sauce/powder raw materials -> raw_material_storage
    bow/cap/pack -> main_storage_1, main_storage_2
    veg ingredients -> main_storage_1

N=10 FG SKUs.
Each SKU_i BOM = sauce_i + powder_i + veg_i + [bow, cap](even i) + [pack](odd i)
Each SKU_i produced by >=2 noodle lines.
"""

from src.edge import TransferMode

# =========================================================================
# Constants
# =========================================================================
N = 10  # Number of FG SKUs

# =========================================================================
# SKU definitions
# =========================================================================

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

# =========================================================================
# Pallet sizes
# =========================================================================
PALLET_SIZE: dict[str, int] = {}
# Raw materials: 100 items/pallet
for sku in _raw_sauce:
    PALLET_SIZE[sku] = 100
for sku in _raw_powder:
    PALLET_SIZE[sku] = 100
for sku in _raw_veg:
    PALLET_SIZE[sku] = 100
for sku in _packaging:
    PALLET_SIZE[sku] = 100
# WIP: 100 items/pallet
for sku in _wip:
    PALLET_SIZE[sku] = 100
# FG: 50 items/pallet
for sku in _fg:
    PALLET_SIZE[sku] = 50

# =========================================================================
# Ingredient selection maps  (for sauce_i, powder_i, veg_i BOMs)
# =========================================================================

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

# FG SKU_i BOM: sauce_i + powder_i + veg_i + [bow, cap](even) + [pack](odd)
def sku_bom_inputs(i: int) -> dict[str, int]:
    """Return the input dict for SKU_i BOM."""
    inputs = {f"sauce_{i}": 1, f"powder_{i}": 1, f"veg_{i}": 1}
    if i % 2 == 0:  # even: bowl + cap
        inputs["bow"] = 1
        inputs["cap"] = 1
    else:  # odd: pack
        inputs["pack"] = 1
    return inputs

# =========================================================================
# Noodle line -> SKU assignment (each SKU produced by >=2 lines)
# =========================================================================
# Main_1 (lines 1-8):
#   1: SKU_1, SKU_6    2: SKU_2, SKU_7    3: SKU_3, SKU_8    4: SKU_4, SKU_9
#   5: SKU_5, SKU_10   6: SKU_1           7: SKU_2           8: SKU_3
# Main_2 (lines 9-16):
#   9: SKU_4           10: SKU_5          11: SKU_6          12: SKU_7
#   13: SKU_8          14: SKU_9          15: SKU_10         16: SKU_1, SKU_6
LINE_SKU_MAP: dict[int, list[int]] = {
    # line_number -> list of SKU indices
    1: [1, 6], 2: [2, 7], 3: [3, 8], 4: [4, 9], 5: [5, 10],
    6: [1], 7: [2], 8: [3],
    9: [4], 10: [5], 11: [6], 12: [7], 13: [8], 14: [9], 15: [10],
    16: [1, 6],
}
# Verify >=2 lines per SKU
_sku_line_count = {i: 0 for i in range(1, N + 1)}
for _lnum, _skus in LINE_SKU_MAP.items():
    for _s in _skus:
        _sku_line_count[_s] += 1
for _i in range(1, N + 1):
    assert _sku_line_count[_i] >= 2, f"SKU_{_i} only has {_sku_line_count[_i]} line(s)"


# =========================================================================
# Nodes
# =========================================================================

NODES: dict[str, dict] = {}

# -- source --
NODES["source"] = {
    "type": "source",
    "display_name": "供应商",
}

# -- raw material storage --
NODES["raw_material_storage"] = {
    "type": "warehouse",
    "max_pallets": 5000,
    "dispatch_interval": 2,
    "dispatch_max_pallets": 50,
    "display_name": "原料库",
}

# -- Sauce production chain (i=1..10) --
for i in range(1, N + 1):
    NODES[f"lineside_sauce_{i}"] = {
        "type": "warehouse",
        "max_pallets": 500,
        "display_name": f"酱包线边仓{i}",
    }
    NODES[f"workstation_sauce_{i}"] = {
        "type": "production",
        "upstream": f"lineside_sauce_{i}",
        "downstream": f"output_sauce_{i}",
        "global_time_step": 5.0,
        "display_name": f"酱包车间{i}",
        "bom": {
            f"sauce_{i}": {
                "inputs": dict(SAUCE_INGREDIENTS[i]),
                "speed": 10.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {f"sauce_{i}": 100},
    }
    NODES[f"output_sauce_{i}"] = {
        "type": "warehouse",
        "max_pallets": 500,
        "display_name": f"酱包产出缓存{i}",
    }

# -- Powder production chain (i=1..6) --
NUM_POWDER_LINES = 6
for i in range(1, NUM_POWDER_LINES + 1):
    NODES[f"lineside_powder_{i}"] = {
        "type": "warehouse",
        "max_pallets": 500,
        "display_name": f"粉包线边仓{i}",
    }
    NODES[f"workstation_powder_{i}"] = {
        "type": "production",
        "upstream": f"lineside_powder_{i}",
        "downstream": f"output_powder_{i}",
        "global_time_step": 5.0,
        "display_name": f"粉包车间{i}",
        # Each powder workstation can produce all 10 powder SKUs
        "bom": {},
        "conversion_factors": {},
    }
    for pi in range(1, N + 1):
        NODES[f"workstation_powder_{i}"]["bom"][f"powder_{pi}"] = {
            "inputs": dict(POWDER_INGREDIENTS[pi]),
            "speed": 10.0,
            "lead_time": 0,
        }
        NODES[f"workstation_powder_{i}"]["conversion_factors"][f"powder_{pi}"] = 100

    NODES[f"output_powder_{i}"] = {
        "type": "warehouse",
        "max_pallets": 500,
        "display_name": f"粉包产出缓存{i}",
    }

# -- WIP storage --
NODES["WIP_storage"] = {
    "type": "warehouse",
    "max_pallets": 3000,
    "display_name": "半成品库",
}

# -- Main storages --
for si in (1, 2):
    NODES[f"main_storage_{si}"] = {
        "type": "warehouse",
        "max_pallets": 3000,
        "display_name": f"{si}库",
    }

# -- Noodle production chain (i=1..16) --
NUM_NOODLE_LINES = 16
for i in range(1, NUM_NOODLE_LINES + 1):
    NODES[f"lineside_noodle_{i}"] = {
        "type": "warehouse",
        "max_pallets": 500,
        "display_name": f"面线边仓{i}",
    }
    # Build BOM for this noodle line based on LINE_SKU_MAP
    bom = {}
    conv = {}
    for sku_idx in LINE_SKU_MAP[i]:
        sku_name = f"SKU_{sku_idx}"
        bom[sku_name] = {
            "inputs": sku_bom_inputs(sku_idx),
            "speed": 5.0,
            "lead_time": 0,
        }
        conv[sku_name] = 50

    NODES[f"workstation_noodle_{i}"] = {
        "type": "production",
        "upstream": f"lineside_noodle_{i}",
        "downstream": f"output_noodle_{i}",
        "global_time_step": 5.0,
        "display_name": f"面线车间{i}",
        "bom": bom,
        "conversion_factors": conv,
    }
    NODES[f"output_noodle_{i}"] = {
        "type": "warehouse",
        "max_pallets": 500,
        "display_name": f"面线产出缓存{i}",
    }

# -- Veg production chain --
NODES["lineside_veg"] = {
    "type": "warehouse",
    "max_pallets": 500,
    "display_name": "菜包线边仓",
}
# workstation_veg can produce all 10 veg SKUs sequentially
# Speed 100 → each SKU: batch_full=int(100*5)=500, one batch of 400 takes 4 min
# Total: 10 SKUs × 4 min = 40 min, finishes at t=45
_veg_bom = {}
_veg_conv = {}
for vi in range(1, N + 1):
    _veg_bom[f"veg_{vi}"] = {
        "inputs": dict(VEG_INGREDIENTS[vi]),
        "speed": 100.0,
        "lead_time": 0,
    }
    _veg_conv[f"veg_{vi}"] = 100

NODES["workstation_veg"] = {
    "type": "production",
    "upstream": "lineside_veg",
    "downstream": "output_veg",
    "global_time_step": 5.0,
    "display_name": "菜包车间",
    "bom": _veg_bom,
    "conversion_factors": _veg_conv,
}
NODES["output_veg"] = {
    "type": "warehouse",
    "max_pallets": 500,
    "display_name": "菜包产出缓存",
}

# -- FG storage --
NODES["fg_storage"] = {
    "type": "warehouse",
    "max_pallets": 2000,
    "display_name": "成品库",
}

# -- Sink --
NODES["sink"] = {
    "type": "sink",
    "display_name": "发货",
}


# =========================================================================
# Edges
# =========================================================================

EDGES: list[dict] = []

# Source -> raw_material_storage (sauce/powder raw materials)
EDGES.append({
    "from_node": "source",
    "to_node": "raw_material_storage",
    "transfer_mode": TransferMode.BATCH,
    "transfer_time": 0.01,
    "batch_size": 999,
})

# Source -> main_storage_1 (veg ingredients + packaging)
EDGES.append({
    "from_node": "source",
    "to_node": "main_storage_1",
    "transfer_mode": TransferMode.BATCH,
    "transfer_time": 0.01,
    "batch_size": 999,
})

# Source -> main_storage_2 (packaging)
EDGES.append({
    "from_node": "source",
    "to_node": "main_storage_2",
    "transfer_mode": TransferMode.BATCH,
    "transfer_time": 0.01,
    "batch_size": 999,
})

# raw_material_storage -> lineside_sauce_i
for i in range(1, N + 1):
    EDGES.append({
        "from_node": "raw_material_storage",
        "to_node": f"lineside_sauce_{i}",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 0.01,
        "batch_size": 999,
    })

# output_sauce_i -> WIP_storage
for i in range(1, N + 1):
    EDGES.append({
        "from_node": f"output_sauce_{i}",
        "to_node": "WIP_storage",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 0.01,
        "batch_size": 999,
    })

# raw_material_storage -> lineside_powder_i
for i in range(1, NUM_POWDER_LINES + 1):
    EDGES.append({
        "from_node": "raw_material_storage",
        "to_node": f"lineside_powder_{i}",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 0.01,
        "batch_size": 999,
    })

# output_powder_i -> WIP_storage
for i in range(1, NUM_POWDER_LINES + 1):
    EDGES.append({
        "from_node": f"output_powder_{i}",
        "to_node": "WIP_storage",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 0.01,
        "batch_size": 999,
    })

# WIP_storage -> main_storage_1, main_storage_2
for si in (1, 2):
    EDGES.append({
        "from_node": "WIP_storage",
        "to_node": f"main_storage_{si}",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 0.01,
        "batch_size": 999,
    })

# main_storage_1 -> lineside_noodle_i (i=1..8)
for i in range(1, 9):
    EDGES.append({
        "from_node": "main_storage_1",
        "to_node": f"lineside_noodle_{i}",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 0.01,
        "batch_size": 999,
    })

# main_storage_2 -> lineside_noodle_i (i=9..16)
for i in range(9, NUM_NOODLE_LINES + 1):
    EDGES.append({
        "from_node": "main_storage_2",
        "to_node": f"lineside_noodle_{i}",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 0.01,
        "batch_size": 999,
    })

# output_noodle_i -> fg_storage
for i in range(1, NUM_NOODLE_LINES + 1):
    EDGES.append({
        "from_node": f"output_noodle_{i}",
        "to_node": "fg_storage",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 0.01,
        "batch_size": 999,
    })

# main_storage_1 -> lineside_veg
EDGES.append({
    "from_node": "main_storage_1",
    "to_node": "lineside_veg",
    "transfer_mode": TransferMode.BATCH,
    "transfer_time": 0.01,
    "batch_size": 999,
})

# output_veg -> main_storage_1, main_storage_2
for si in (1, 2):
    EDGES.append({
        "from_node": "output_veg",
        "to_node": f"main_storage_{si}",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 0.01,
        "batch_size": 999,
    })

# fg_storage -> sink
EDGES.append({
    "from_node": "fg_storage",
    "to_node": "sink",
    "transfer_mode": TransferMode.BATCH,
    "transfer_time": 0.01,
    "batch_size": 999,
})

# =========================================================================
# Simulation duration
# =========================================================================
SIM_DURATION = 5000
