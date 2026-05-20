"""Plant topology: a single production line with raw storage and FG storage.

  source -> raw_wh -> prod -> fg_wh -> sink
"""
from src.infrastructure.edge import TransferMode
from scenario_example.bom import FG_BOM

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
NODES: dict[str, dict] = {}

NODES["source"] = {"type": "source", "display_name": "Supplier"}

NODES["raw_wh"] = {
    "type": "warehouse",
    "max_pallets": 100,
    "display_name": "Raw Material Warehouse",
}

NODES["prod"] = {
    "type": "production",
    "upstream": "raw_wh",
    "downstream": "fg_wh",
    "global_time_step": 20.0,
    "retry_delay": 1.0,
    "display_name": "Workstation",
    "bom": dict(FG_BOM),
    "conversion_factors": {"fg_x": 1, "fg_y": 1},
}

NODES["fg_wh"] = {
    "type": "warehouse",
    "max_pallets": 100,
    "display_name": "FG Warehouse",
}

NODES["sink"] = {"type": "sink", "display_name": "Customer"}

# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------
EDGES: list[dict] = []

# source -> raw_wh: fast batch transport
EDGES.append({
    "from_node": "source",
    "to_node": "raw_wh",
    "transfer_mode": TransferMode.PER_PALLET,
    "batch_transport_time": 0.01,
})

# fg_wh -> sink: fast batch transport
EDGES.append({
    "from_node": "fg_wh",
    "to_node": "sink",
    "transfer_mode": TransferMode.PER_PALLET,
    "batch_transport_time": 0.01,
})
