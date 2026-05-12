"""Simulation configuration: Source -> RawMaterialWH -> Production -> ProductWH -> Sink.

Two input SKUs (wip_X, wip_Y) feed into the production line which outputs
SKU_A.  BOM: 1x wip_X + 1x wip_Y = 1x SKU_A, speed=10/min, lead_time=5min,
global_time_step=10min.
"""

from src.edge import TransferMode

SKUS = ["wip_X", "wip_Y", "SKU_A"]

PALLET_SIZE = {
    "wip_X": 100,
    "wip_Y": 100,
    "SKU_A": 50,
}

NODES = {
    "Source": {
        "type": "source",
        "dispatch_interval": 1,
        "dispatch_max_pallets": 999,
    },
    "RawMaterialWH": {
        "type": "warehouse",
        "max_pallets": 1000,
        "dispatch_interval": 5,
        "dispatch_max_pallets": 10,
    },
    "ProductionLine": {
        "type": "production",
        "upstream": "RawMaterialWH",
        "downstream": "ProductWH",
        "global_time_step": 10.0,
        "bom": {
            "SKU_A": {
                "inputs": {"wip_X": 1, "wip_Y": 1},
                "speed": 10.0,
                "lead_time": 5.0,
            },
        },
        "conversion_factors": {"SKU_A": 50},
    },
    "ProductWH": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 5,
        "dispatch_max_pallets": 10,
    },
    "Sink": {
        "type": "sink",
    },
}

EDGES = [
    {
        "from_node": "Source",
        "to_node": "RawMaterialWH",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 50,
    },
    {
        "from_node": "ProductWH",
        "to_node": "Sink",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 20,
    },
]

SIM_DURATION = 200
