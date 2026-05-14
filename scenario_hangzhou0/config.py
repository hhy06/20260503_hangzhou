"""Simulation configuration for Hangzhou warehouse scenario.

SKU IDs <-> Display names:
  raw            -> 原料
  sauce_wip      -> 酱包
  powder_wip     -> 粉包
  veg_wip        -> 菜包
  fg_noodle      -> 成品面

Flow:
  source (供应商)
    -> raw_material_wh (调理原料库)
      -> seasoning_lineside (common line-side 边仓 for 酱包/粉包/菜包)
        -> sauce_workshop (酱包车间)  --produces sauce_wip--> semi_finished_wh
        -> powder_workshop (粉包车间) --produces powder_wip--> semi_finished_wh
      -> semi_finished_wh (半成品库)
        -> warehouse_1 (一库) -> line_side_1 (边仓) -> noodle_ws_1 (一制面车间) --produces fg_noodle--> finished_wh
        -> warehouse_2 (二库) -> line_side_2 (边仓) -> noodle_ws_2 (二制面车间) --produces fg_noodle--> finished_wh
      -> finished_wh (成品库) -> sink (发货)

Simplest BOM:
  sauce_workshop:  1x raw -> 1x sauce_wip
  powder_workshop: 1x raw -> 1x powder_wip
  noodle_ws_1:     1x sauce_wip -> 1x fg_noodle
  noodle_ws_2:     1x powder_wip -> 1x fg_noodle
"""

from src.edge import TransferMode

SKUS = {
    "raw": "原料",
    "sauce_wip": "酱包",
    "powder_wip": "粉包",
    "veg_wip": "菜包",
    "fg_noodle": "成品面",
}

PALLET_SIZE = {
    "raw": 100,
    "sauce_wip": 100,
    "powder_wip": 100,
    "veg_wip": 100,
    "fg_noodle": 50,
}

NODES = {
    "source": {
        "type": "source",
        "dispatch_interval": 1,
        "dispatch_max_pallets": 999,
        "display_name": "供应商",
    },
    "raw_material_wh": {
        "type": "warehouse",
        "max_pallets": 2000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "调理原料库",
    },
    "seasoning_lineside": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "粉酱线边仓",
    },
    "sauce_workshop": {
        "type": "production",
        "upstream": "seasoning_lineside",
        "downstream": "semi_finished_wh",
        "global_time_step": 10.0,
        "bom": {
            "sauce_wip": {
                "inputs": {"raw": 1},
                "speed": 10.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"sauce_wip": 100},
        "display_name": "酱包车间",
    },
    "powder_workshop": {
        "type": "production",
        "upstream": "seasoning_lineside",
        "downstream": "semi_finished_wh",
        "global_time_step": 10.0,
        "bom": {
            "powder_wip": {
                "inputs": {"raw": 1},
                "speed": 10.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"powder_wip": 100},
        "display_name": "粉包车间",
    },
    "semi_finished_wh": {
        "type": "warehouse",
        "max_pallets": 1000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "半成品库",
    },
    "warehouse_1": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "一库",
    },
    "warehouse_2": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "二库",
    },
    "line_side_1": {
        "type": "warehouse",
        "max_pallets": 200,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 10,
        "display_name": "一面线边仓",
    },
    "line_side_2": {
        "type": "warehouse",
        "max_pallets": 200,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 10,
        "display_name": "二面线边仓",
    },
    "noodle_ws_1": {
        "type": "production",
        "upstream": "line_side_1",
        "downstream": "finished_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg_noodle": {
                "inputs": {"sauce_wip": 1},
                "speed": 5.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg_noodle": 50},
        "display_name": "一制面车间",
    },
    "noodle_ws_2": {
        "type": "production",
        "upstream": "line_side_2",
        "downstream": "finished_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg_noodle": {
                "inputs": {"powder_wip": 1},
                "speed": 5.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg_noodle": 50},
        "display_name": "二制面车间",
    },
    "finished_wh": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "成品库",
    },
    "sink": {
        "type": "sink",
        "display_name": "发货",
    },
}

EDGES = [
    {
        "from_node": "source",
        "to_node": "raw_material_wh",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 50,
    },
    {
        "from_node": "raw_material_wh",
        "to_node": "seasoning_lineside",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 50,
    },
    {
        "from_node": "semi_finished_wh",
        "to_node": "warehouse_1",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 50,
    },
    {
        "from_node": "semi_finished_wh",
        "to_node": "warehouse_2",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 50,
    },
    {
        "from_node": "warehouse_1",
        "to_node": "line_side_1",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 50,
    },
    {
        "from_node": "warehouse_2",
        "to_node": "line_side_2",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 50,
    },
    {
        "from_node": "finished_wh",
        "to_node": "sink",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 50,
    },
]

SIM_DURATION = 20000
