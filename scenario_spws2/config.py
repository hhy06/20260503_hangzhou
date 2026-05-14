"""Simulation configuration: Source -> RawWH -> ProductionLine -> Warehouse -> Sink.

Four output SKUs share one production line, running sequentially:
  - sku_a: speed 10/min,  qty 100  -> finishes in 10 min
  - sku_b: speed  5/min,  qty 200  -> finishes in 40 min
  - sku_c: speed  2/min,  qty 300  -> finishes in 150 min
  - sku_d: speed  1/min,  qty 400  -> finishes in 400 min

SIM_DURATION=120 is long enough for sku_a + sku_b to finish,
sku_c to be ~half-done, and sku_d to never start.
"""

from src.edge import TransferMode

SKUS = ["raw", "sku_a", "sku_b", "sku_c", "sku_d"]

PALLET_SIZE = {
    "raw": 100,
    "sku_a": 50,
    "sku_b": 50,
    "sku_c": 50,
    "sku_d": 50,
}

NODES = {
    "source": {
        "type": "source",
        "dispatch_interval": 1,
        "dispatch_max_pallets": 999,
    },
    "raw_wh": {
        "type": "warehouse",
        "max_pallets": 2000,
        "dispatch_interval": 5,
        "dispatch_max_pallets": 10,
    },
    "productionline": {
        "type": "production",
        "upstream": "raw_wh",
        "downstream": "warehouse",
        "global_time_step": 10.0,
        "bom": {
            "sku_a": {
                "inputs": {"raw": 1},
                "speed": 10.0,
                "lead_time": 0,
            },
            "sku_b": {
                "inputs": {"raw": 1},
                "speed": 5.0,
                "lead_time": 0,
            },
            "sku_c": {
                "inputs": {"raw": 2},
                "speed": 2.0,
                "lead_time": 0,
            },
            "sku_d": {
                "inputs": {"raw": 1},
                "speed": 1.0,
                "lead_time": 0,
            },
        },
        "conversion_factors": {
            "sku_a": 50,
            "sku_b": 50,
            "sku_c": 50,
            "sku_d": 50,
        },
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

SIM_DURATION = 120
