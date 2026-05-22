"""Simulation configuration for the Hangzhou scenario.

This file is the single entry-point for the scenario.  It delegates
specific categories of information to specialised sub-modules:

    sku.py             SKU definitions + pallet sizes
    bom.py             Bill-of-materials (ingredient maps)
    plant_topology.py  Node and edge definitions

Any consumer that does ``from scenario.hangzhou0b import config`` gets
access to all the names below on ``config.*``.
"""

# ---------------------------------------------------------------------------
# SKU definitions
# ---------------------------------------------------------------------------
from .sku import (
    N,
    SKUS,
    PALLET_SIZE,
)

# ---------------------------------------------------------------------------
# Bill-of-materials  (ingredient maps, FG BOM helper, line→SKU assignment)
# ---------------------------------------------------------------------------
from .bom import (
    SAUCE_INGREDIENTS,
    POWDER_INGREDIENTS,
    VEG_INGREDIENTS,
    LINE_SKU_MAP,
    sku_bom_inputs,
)

# ---------------------------------------------------------------------------
# Plant topology  (nodes + edges)
# ---------------------------------------------------------------------------
from .plant_topology import (
    NODES,
    EDGES,
    NUM_POWDER_LINES,
    NUM_NOODLE_LINES,
)

# ---------------------------------------------------------------------------
# Management strategy
# ---------------------------------------------------------------------------
MANAGEMENT = {
    "type": "safe_stock",
    "decision_interval": 10.0,
}

# ---------------------------------------------------------------------------
# Simulation duration
# ---------------------------------------------------------------------------
SIM_DURATION = 5000


def dump_config() -> None:
    """Print all configuration data for inspection."""
    from collections.abc import Mapping, Sequence
    from .config_static_jobs import TRANSPORT_ORDERS, PRODUCTION_JOBS
    from .safe_stock import SAFE_STOCK, DEMAND_ORDERS

    items = {
        "N": N,
        "SKUS": SKUS,
        "PALLET_SIZE": PALLET_SIZE,
        "SAUCE_INGREDIENTS": SAUCE_INGREDIENTS,
        "POWDER_INGREDIENTS": POWDER_INGREDIENTS,
        "VEG_INGREDIENTS": VEG_INGREDIENTS,
        "LINE_SKU_MAP": LINE_SKU_MAP,
        "NODES": NODES,
        "EDGES": EDGES,
        "NUM_POWDER_LINES": NUM_POWDER_LINES,
        "NUM_NOODLE_LINES": NUM_NOODLE_LINES,
        "TRANSPORT_ORDERS": TRANSPORT_ORDERS,
        "PRODUCTION_JOBS": PRODUCTION_JOBS,
        "SAFE_STOCK": SAFE_STOCK,
        "DEMAND_ORDERS": DEMAND_ORDERS,
        "MANAGEMENT": MANAGEMENT,
        "SIM_DURATION": SIM_DURATION,
    }

    print("=" * 60)
    print("  CONFIG DUMP")
    print("=" * 60)

    for name, val in items.items():
        print(f"\n  {name}")
        if isinstance(val, Mapping):
            print(f"    dict  ({len(val)} keys)")
            for k in list(val.keys())[:3]:
                v = val[k]
                r = repr(v)
                if len(r) > 80:
                    r = r[:77] + "..."
                print(f"      {k!r}: {r}")
            if len(val) > 3:
                print(f"      ... +{len(val) - 3} more keys")
        elif isinstance(val, Sequence) and not isinstance(val, str):
            print(f"    list  ({len(val)} items)")
            if len(val) > 0:
                r = repr(val[0])
                if len(r) > 80:
                    r = r[:77] + "..."
                print(f"      first: {r}")
        else:
            print(f"    = {val!r}")

    print("\n" + "=" * 60)
