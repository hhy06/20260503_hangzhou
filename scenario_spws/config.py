"""Simulation configuration: Source -> RawWH -> ProductionLine -> Warehouse -> Sink.

Two output SKUs share one production line:
  - sku_a: BOM 3x raw per unit, speed 1 item/min
  - sku_b: BOM 2x raw per unit, speed 2 items/min
"""

from src.edge import TransferMode

SKUS = ["raw", "sku_a", "sku_b"]

PALLET_SIZE = {
    "raw": 100,
    "sku_a": 50,
    "sku_b": 50,
}

NODES = {
    "source": {
        "type": "source",
        "dispatch_interval": 1,
        "dispatch_max_pallets": 999,
    },
    "raw_wh": {
        "type": "warehouse",
        "max_pallets": 1000,
        "dispatch_interval": 5,
        "dispatch_max_pallets": 10,
    },
    "productionlien": {
        "type": "production",
        "upstream": "raw_wh",
        "downstream": "warehouse",
        "global_time_step": 10.0,
        "bom": {
            "sku_a": {
                "inputs": {"raw": 3},
                "speed": 1.0,
                "lead_time": 0,
            },
            "sku_b": {
                "inputs": {"raw": 2},
                "speed": 2.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {"sku_a": 50, "sku_b": 50},
    },
    "warehouse": {
        "type": "warehouse",
        "max_pallets": 500,
        "dispatch_interval": 5,
        "dispatch_max_pallets": 10,
    },
    "sink": {
        "type": "sink",
    },
}

EDGES = [
    {
        "from_node": "source",
        "to_node": "raw_wh",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 50,
    },
    {
        "from_node": "warehouse",
        "to_node": "sink",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 50,
    },
]

SIM_DURATION = 200
