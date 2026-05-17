"""Simulation configuration for hangzhou1 — 10-SKU dynamic demand scenario.

SKUs (10)
---------
raw, wip_a, wip_b, fg_a1, fg_a2, fg_a3, fg_b1, fg_b2, fg_b3, fg_b4

Flow
----
  source
    -> raw_wh (原料库)
      -> line_side (线边仓)
        -> factory_a  ---produces wip_a--> semi_wh (半成品库)
        -> factory_b  ---produces wip_b--> semi_wh
      -> semi_wh
        -> wh_a ---> line_a_side --> packing_a1/2/3 ---produces fg_a*--> fg_wh
        -> wh_b ---> line_b_side --> packing_b1/2/3/4 ---produces fg_b*--> fg_wh
      -> fg_wh (成品库) -> sink (发货)

BOM
---
  factory_a:   1 raw    -> 1 wip_a      (speed=10/min)
  factory_b:   1 raw    -> 1 wip_b      (speed=10/min)
  packing_a1:  1 wip_a  -> 1 fg_a1      (speed=5/min)
  packing_a2:  1 wip_a  -> 1 fg_a2      (speed=5/min)
  packing_a3:  1 wip_a  -> 1 fg_a3      (speed=5/min)
  packing_b1:  1 wip_b  -> 1 fg_b1      (speed=4/min)
  packing_b2:  1 wip_b  -> 1 fg_b2      (speed=4/min)
  packing_b3:  1 wip_b  -> 1 fg_b3      (speed=4/min)
  packing_b4:  1 wip_b  -> 1 fg_b4      (speed=4/min)
"""

from src.edge import TransferMode

SKUS = {
    "raw": "原料",
    "wip_a": "酱包A",
    "wip_b": "粉包B",
    "fg_a1": "成品A1",
    "fg_a2": "成品A2",
    "fg_a3": "成品A3",
    "fg_b1": "成品B1",
    "fg_b2": "成品B2",
    "fg_b3": "成品B3",
    "fg_b4": "成品B4",
}

PALLET_SIZE = {
    "raw": 100,
    "wip_a": 100,
    "wip_b": 100,
    "fg_a1": 50,
    "fg_a2": 50,
    "fg_a3": 50,
    "fg_b1": 50,
    "fg_b2": 50,
    "fg_b3": 50,
    "fg_b4": 50,
}

# ---------------------------------------------------------------------------
# Node definitions
# ---------------------------------------------------------------------------

NODES = {
    # -- supply --
    "source": {
        "type": "source",
        "dispatch_interval": 1,
        "dispatch_max_pallets": 999,
        "display_name": "供应商",
    },
    "raw_wh": {
        "type": "warehouse",
        "max_pallets": 2000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "原料库",
    },
    "line_side": {
        "type": "warehouse",
        "max_pallets": 1000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "线边仓",
    },
    # -- WIP factories --
    "factory_a": {
        "type": "production",
        "upstream": "line_side",
        "downstream": "semi_wh",
        "global_time_step": 10.0,
        "bom": {
            "wip_a": {
                "inputs": {"raw": 1},
                "speed": 10.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"wip_a": 100},
        "display_name": "酱包车间A",
    },
    "factory_b": {
        "type": "production",
        "upstream": "line_side",
        "downstream": "semi_wh",
        "global_time_step": 10.0,
        "bom": {
            "wip_b": {
                "inputs": {"raw": 1},
                "speed": 10.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"wip_b": 100},
        "display_name": "粉包车间B",
    },
    # -- central WIP storage --
    "semi_wh": {
        "type": "warehouse",
        "max_pallets": 2000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "半成品库",
    },
    # -- A-side distribution --
    "wh_a": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "A库",
    },
    "line_a_side": {
        "type": "warehouse",
        "max_pallets": 400,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "A线边仓",
    },
    # -- A-side packing lines --
    "packing_a1": {
        "type": "production",
        "upstream": "line_a_side",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg_a1": {
                "inputs": {"wip_a": 1},
                "speed": 5.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg_a1": 50},
        "display_name": "包装A1",
    },
    "packing_a2": {
        "type": "production",
        "upstream": "line_a_side",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg_a2": {
                "inputs": {"wip_a": 1},
                "speed": 5.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg_a2": 50},
        "display_name": "包装A2",
    },
    "packing_a3": {
        "type": "production",
        "upstream": "line_a_side",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg_a3": {
                "inputs": {"wip_a": 1},
                "speed": 5.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg_a3": 50},
        "display_name": "包装A3",
    },
    # -- B-side distribution --
    "wh_b": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "B库",
    },
    "line_b_side": {
        "type": "warehouse",
        "max_pallets": 400,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "B线边仓",
    },
    # -- B-side packing lines --
    "packing_b1": {
        "type": "production",
        "upstream": "line_b_side",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg_b1": {
                "inputs": {"wip_b": 1},
                "speed": 4.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg_b1": 50},
        "display_name": "包装B1",
    },
    "packing_b2": {
        "type": "production",
        "upstream": "line_b_side",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg_b2": {
                "inputs": {"wip_b": 1},
                "speed": 4.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg_b2": 50},
        "display_name": "包装B2",
    },
    "packing_b3": {
        "type": "production",
        "upstream": "line_b_side",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg_b3": {
                "inputs": {"wip_b": 1},
                "speed": 4.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg_b3": 50},
        "display_name": "包装B3",
    },
    "packing_b4": {
        "type": "production",
        "upstream": "line_b_side",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg_b4": {
                "inputs": {"wip_b": 1},
                "speed": 4.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg_b4": 50},
        "display_name": "包装B4",
    },
    # -- finished goods --
    "fg_wh": {
        "type": "warehouse",
        "max_pallets": 2000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "成品库",
    },
    "sink": {
        "type": "sink",
        "display_name": "发货",
    },
}

# ---------------------------------------------------------------------------
# Transport edges  (warehouse → warehouse)
# ---------------------------------------------------------------------------

EDGES = [
    {"from_node": "source", "to_node": "raw_wh",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
    {"from_node": "raw_wh", "to_node": "line_side",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
    {"from_node": "semi_wh", "to_node": "wh_a",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
    {"from_node": "semi_wh", "to_node": "wh_b",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
    {"from_node": "wh_a", "to_node": "line_a_side",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
    {"from_node": "wh_b", "to_node": "line_b_side",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
    {"from_node": "fg_wh", "to_node": "sink",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
]

SIM_DURATION = 15000   # ~10.4 days  (1 day = 1440)

# Day length in simulation minutes
DAY = 1440
