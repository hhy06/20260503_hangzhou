"""Simulation configuration for the Hangzhou scenario.

This file is the single entry-point for the scenario.  It delegates
specific categories of information to specialised sub-modules:

    sku.py             SKU definitions + pallet sizes
    bom.py             Bill-of-materials (ingredient maps)
    plant_topology.py  Node and edge definitions

Any consumer that does ``from scenario_hangzhou0 import config`` gets
access to all the names below on ``config.*``.
"""

# ---------------------------------------------------------------------------
# SKU definitions
# ---------------------------------------------------------------------------
from scenario_hangzhou0.sku import (
    N,
    SKUS,
    PALLET_SIZE,
)

# ---------------------------------------------------------------------------
# Bill-of-materials  (ingredient maps, FG BOM helper, line→SKU assignment)
# ---------------------------------------------------------------------------
from scenario_hangzhou0.bom import (
    SAUCE_INGREDIENTS,
    POWDER_INGREDIENTS,
    VEG_INGREDIENTS,
    LINE_SKU_MAP,
    sku_bom_inputs,
)

# ---------------------------------------------------------------------------
# Plant topology  (nodes + edges)
# ---------------------------------------------------------------------------
from scenario_hangzhou0.plant_topology import (
    NODES,
    EDGES,
    NUM_POWDER_LINES,
    NUM_NOODLE_LINES,
)

# ---------------------------------------------------------------------------
# Management strategy
# ---------------------------------------------------------------------------
MANAGEMENT = {
    "type": "static_order",
    "decision_interval": 10.0,
}

# ---------------------------------------------------------------------------
# Simulation duration
# ---------------------------------------------------------------------------
SIM_DURATION = 5000
