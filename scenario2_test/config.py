"""Minimal test config: Source -> Warehouse -> Sink, one SKU."""

from src.edge import TransferMode

SKUS = ["SKU_X"]

PALLET_SIZE = {
    "SKU_X": 10,
}

NODES = {
    "Source": {
        "type": "source",
        "dispatch_interval": 1,
        "dispatch_max_pallets": 999,
    },
    "Warehouse": {
        "type": "warehouse",
        "max_pallets": 1000,
        "dispatch_interval": 1,
        "dispatch_max_pallets": 10,
    },
    "Sink": {
        "type": "sink",
    },
}

EDGES = [
    {
        "from_node": "Source",
        "to_node": "Warehouse",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 10,
    },
    {
        "from_node": "Warehouse",
        "to_node": "Sink",
        "transfer_mode": TransferMode.BATCH,
        "transfer_time": 1,
        "batch_size": 5,
    },
]

SIM_DURATION = 50
