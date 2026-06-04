"""Plant topology: node definitions and edge connections.

Depends on ``sku.N`` for counts and ``bom`` for ingredient maps.

This module could be replaced by a JSON reader or generator in future.
"""

from src.infrastructure.edge import TransferMode

from .sku import N
from .bom import (
    SAUCE_INGREDIENTS,
    POWDER_INGREDIENTS,
    VEG_INGREDIENTS,
    LINE_SKU_MAP,
    sku_bom_inputs,
)

# Number of production lines per product type
NUM_POWDER_LINES = 6
NUM_NOODLE_LINES = 16

# =========================================================================
# Nodes
# =========================================================================

NODES: dict[str, dict] = {}

# -- source --
NODES["source"] = {"type": "source", "display_name": "供应商"}

# -- raw material storage --
NODES["raw_material_storage"] = {
    "type": "warehouse",
    "max_pallets": 5000,
    "dispatch_interval": 2,
    "dispatch_max_pallets": 50,
    "display_name": "原料库",
}

# -- Sauce production chain (i=1..N) --
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
                "lead_time": 0,
            },
        },
    }
    NODES[f"output_sauce_{i}"] = {
        "type": "warehouse",
        "max_pallets": 500,
        "display_name": f"酱包产出缓存{i}",
    }

# -- Powder production chain (i=1..NUM_POWDER_LINES) --
for i in range(1, NUM_POWDER_LINES + 1):
    NODES[f"lineside_powder_{i}"] = {
        "type": "warehouse",
        "max_pallets": 500,
        "display_name": f"粉包线边仓{i}",
    }
    bom = {}
    for pi in range(1, N + 1):
        bom[f"powder_{pi}"] = {
            "inputs": dict(POWDER_INGREDIENTS[pi]),
            "lead_time": 0,
        }
    NODES[f"workstation_powder_{i}"] = {
        "type": "production",
        "upstream": f"lineside_powder_{i}",
        "downstream": f"output_powder_{i}",
        "global_time_step": 5.0,
        "display_name": f"粉包车间{i}",
        "bom": bom,
    }
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

# -- Noodle production chain (i=1..NUM_NOODLE_LINES) --
for i in range(1, NUM_NOODLE_LINES + 1):
    NODES[f"lineside_noodle_{i}"] = {
        "type": "warehouse",
        "max_pallets": 500,
        "display_name": f"面线边仓{i}",
    }
    bom = {}
    for sku_idx in LINE_SKU_MAP[i]:
        sku_name = f"SKU_{sku_idx}"
        bom[sku_name] = {
            "inputs": sku_bom_inputs(sku_idx),
            "lead_time": 0,
        }
    NODES[f"workstation_noodle_{i}"] = {
        "type": "production",
        "upstream": f"lineside_noodle_{i}",
        "downstream": f"output_noodle_{i}",
        "global_time_step": 5.0,
        "display_name": f"面线车间{i}",
        "bom": bom,
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
_veg_bom = {}
for vi in range(1, N + 1):
    _veg_bom[f"veg_{vi}"] = {
        "inputs": dict(VEG_INGREDIENTS[vi]),
        "lead_time": 0,
    }
NODES["workstation_veg"] = {
    "type": "production",
    "upstream": "lineside_veg",
    "downstream": "output_veg",
    "global_time_step": 5.0,
    "display_name": "菜包车间",
    "bom": _veg_bom,
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
NODES["sink"] = {"type": "sink", "display_name": "发货"}


# =========================================================================
# Edges
# =========================================================================

EDGES: list[dict] = []

# Source -> raw_material_storage (sauce / powder raw materials)
EDGES.append({
    "from_node": "source",
    "to_node": "raw_material_storage",
    "transfer_mode": TransferMode.BATCH,
    "batch_transport_time": 5.0,
    "batch_pallets": 24,
})

# Source -> main_storage_1 (veg ingredients + packaging)
EDGES.append({
    "from_node": "source",
    "to_node": "main_storage_1",
    "transfer_mode": TransferMode.BATCH,
    "batch_transport_time": 5.0,
    "batch_pallets": 24,
})

# Source -> main_storage_2 (packaging)
EDGES.append({
    "from_node": "source",
    "to_node": "main_storage_2",
    "transfer_mode": TransferMode.BATCH,
    "batch_transport_time": 5.0,
    "batch_pallets": 24,
})

# raw_material_storage -> lineside_sauce_i
for i in range(1, N + 1):
    EDGES.append({
        "from_node": "raw_material_storage",
        "to_node": f"lineside_sauce_{i}",
        "transfer_mode": TransferMode.BATCH,
        "batch_transport_time": 10.0,
        "batch_pallets": 10,
    })

# output_sauce_i -> WIP_storage
for i in range(1, N + 1):
    EDGES.append({
        "from_node": f"output_sauce_{i}",
        "to_node": "WIP_storage",
        "transfer_mode": TransferMode.BATCH,
        "batch_transport_time": 10.0,
        "batch_pallets": 10,
    })

# raw_material_storage -> lineside_powder_i
for i in range(1, NUM_POWDER_LINES + 1):
    EDGES.append({
        "from_node": "raw_material_storage",
        "to_node": f"lineside_powder_{i}",
        "transfer_mode": TransferMode.BATCH,
        "batch_transport_time": 10.0,
        "batch_pallets": 10,
    })

# output_powder_i -> WIP_storage
for i in range(1, NUM_POWDER_LINES + 1):
    EDGES.append({
        "from_node": f"output_powder_{i}",
        "to_node": "WIP_storage",
        "transfer_mode": TransferMode.BATCH,
        "batch_transport_time": 10.0,
        "batch_pallets": 10,
    })

# WIP_storage -> main_storage_1, main_storage_2  (fast batch for dynamic replenishment)
for si in (1, 2):
    EDGES.append({
        "from_node": "WIP_storage",
        "to_node": f"main_storage_{si}",
        "transfer_mode": TransferMode.BATCH,
        "batch_transport_time": 1.0,
        "batch_pallets": 24,
    })

# main_storage_1 -> lineside_noodle_i (i=1..8)
for i in range(1, 9):
    EDGES.append({
        "from_node": "main_storage_1",
        "to_node": f"lineside_noodle_{i}",
        "transfer_mode": TransferMode.BATCH,
        "batch_transport_time": 10.0,
        "batch_pallets": 10,
    })

# main_storage_2 -> lineside_noodle_i (i=9..16)
for i in range(9, NUM_NOODLE_LINES + 1):
    EDGES.append({
        "from_node": "main_storage_2",
        "to_node": f"lineside_noodle_{i}",
        "transfer_mode": TransferMode.BATCH,
        "batch_transport_time": 10.0,
        "batch_pallets": 10,
    })

# output_noodle_i -> fg_storage
for i in range(1, NUM_NOODLE_LINES + 1):
    EDGES.append({
        "from_node": f"output_noodle_{i}",
        "to_node": "fg_storage",
        "transfer_mode": TransferMode.BATCH,
        "batch_transport_time": 10.0,
        "batch_pallets": 10,
    })

# main_storage_1 -> lineside_veg
EDGES.append({
    "from_node": "main_storage_1",
    "to_node": "lineside_veg",
    "transfer_mode": TransferMode.BATCH,
    "batch_transport_time": 10.0,
    "batch_pallets": 10,
})

# output_veg -> main_storage_1, main_storage_2
for si in (1, 2):
    EDGES.append({
        "from_node": "output_veg",
        "to_node": f"main_storage_{si}",
        "transfer_mode": TransferMode.BATCH,
        "batch_transport_time": 10.0,
        "batch_pallets": 10,
    })

# fg_storage -> sink
EDGES.append({
    "from_node": "fg_storage",
    "to_node": "sink",
    "transfer_mode": TransferMode.BATCH,
    "batch_transport_time": 5.0,
    "batch_pallets": 24,
})
