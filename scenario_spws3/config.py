from src.edge import TransferMode

SKUS = {
    "raw": "原料",
    "fg_a": "成品A",
    "fg_b": "成品B",
}

PALLET_SIZE = {
    "raw": 100,
    "fg_a": 50,
    "fg_b": 50,
}

NODES = {
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
    "workstation": {
        "type": "production",
        "upstream": "raw_wh",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": {
            "fg_a": {
                "inputs": {"raw": 2},
                "speed": 5.0,
                "lead_time": 0,
            },
            "fg_b": {
                "inputs": {"raw": 3},
                "speed": 4.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"fg_a": 50, "fg_b": 50},
        "display_name": "产线",
    },
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

EDGES = [
    {"from_node": "source", "to_node": "raw_wh",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
    {"from_node": "fg_wh", "to_node": "sink",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
]

BASIC_TIME_UNIT = "MINUTE"
SIM_DURATION = 8000
DAY = 60 * 24
SHIFT_STARTS = [480, 1200]
SHIFT_DURATION = 690
