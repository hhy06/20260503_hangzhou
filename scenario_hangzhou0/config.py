"""Simulation configuration for Hangzhou warehouse scenario.

Flow:
  source (供应商)
    -> raw_material_wh (调理原料库)
      -> seasoning_lineside (common line-side 边仓 for 酱包/粉包)
        -> sauce_workshop (酱包车间)  --produces wip_s--> semi_finished_wh
        -> powder_workshop (粉包车间) --produces wip_p--> semi_finished_wh
      -> semi_finished_wh (半成品库)
        -> warehouse_1 (一库) -> line_side_1 (边仓) -> noodle_ws_1 (一制面车间) --produces fg--> finished_wh
        -> warehouse_2 (二库) -> line_side_2 (边仓) -> noodle_ws_2 (二制面车间) --produces fg--> finished_wh
      -> finished_wh (成品库) -> sink (发货)

Simplest BOM:
  sauce_workshop:  1x raw -> 1x wip_s
  powder_workshop: 1x raw -> 1x wip_p
  noodle_ws_1:     1x wip_s -> 1x fg   (一制面 uses sauce packet)
  noodle_ws_2:     1x wip_p -> 1x fg   (二制面 uses powder packet)
"""

from src.edge import TransferMode

SKUS = ["raw", "wip_s", "wip_p", "fg"]

PALLET_SIZE = {
    "raw": 100,
    "wip_s": 100,
    "wip_p": 100,
    "fg": 50,
}

NODES = {
    "source": {
        "type": "source",
        "dispatch_interval": 1,
        "dispatch_max_pallets": 999,
    },
    "raw_material_wh": {
        "type": "warehouse",
        "max_pallets": 2000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
    },
    "seasoning_lineside": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
    },
    "sauce_workshop": {
        "type": "production",
        "upstream": "seasoning_lineside",
        "downstream": "semi_finished_wh",
        "global_time_step": 10.0,
        "bom": {
            "wip_s": {
                "inputs": {"raw": 1},
                "speed": 10.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"wip_s": 100},
    },
    "powder_workshop": {
        "type": "production",
        "upstream": "seasoning_lineside",
        "downstream": "semi_finished_wh",
        "global_time_step": 10.0,
        "bom": {
            "wip_p": {
                "inputs": {"raw": 1},
                "speed": 10.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"wip_p": 100},
    },
    "semi_finished_wh": {
        "type": "warehouse",
        "max_pallets": 1000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
    },
    "warehouse_1": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
    },
    "warehouse_2": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
    },
    "line_side_1": {
        "type": "warehouse",
        "max_pallets": 200,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 10,
    },
    "line_side_2": {
        "type": "warehouse",
        "max_pallets": 200,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 10,
    },
    "noodle_ws_1": {
        "type": "production",
        "upstream": "line_side_1",
        "downstream": "finished_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg": {
                "inputs": {"wip_s": 1},
                "speed": 5.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg": 50},
    },
    "noodle_ws_2": {
        "type": "production",
        "upstream": "line_side_2",
        "downstream": "finished_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg": {
                "inputs": {"wip_p": 1},
                "speed": 5.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg": 50},
    },
    "finished_wh": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
    },
    "sink": {
        "type": "sink",
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

SIM_DURATION = 200
