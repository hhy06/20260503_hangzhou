"""Simulation configuration: nodes, edges, SKUs, and constants."""

from src.edge import TransferMode

SKUS = ["SKU_A", "SKU_B", "SKU_C"]

PALLET_SIZE = {
    "SKU_A": 50,
    "SKU_B": 20,
    "SKU_C": 100,
}

NODES = {
    "Source": {
        "max_pallets": None,
        "type": "source",
        "dispatch_interval": 1,
        "dispatch_max_pallets": 999,
    },
    "WarehouseA": {
        "max_pallets": 100,
        "type": "warehouse",
        "dispatch_interval": 5,
        "dispatch_max_pallets": 3,
    },
    "WarehouseB": {
        "max_pallets": 80,
        "type": "warehouse",
        "dispatch_interval": 5,
        "dispatch_max_pallets": 2,
    },
    "Sink": {
        "max_pallets": None,
        "type": "sink",
        "dispatch_interval": 1,
        "dispatch_max_pallets": 999,
    },
}

EDGES = [
    {
        "from_node": "Source",
        "to_node": "WarehouseA",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 3,
        "batch_size": 10,
    },
    {
        "from_node": "WarehouseA",
        "to_node": "WarehouseB",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 10,
        "batch_size": 5,
    },
    {
        "from_node": "WarehouseB",
        "to_node": "Sink",
        "transfer_mode": TransferMode.PER_PALLET,
        "transfer_time": 2,
    },
]

SIM_DURATION = 200
