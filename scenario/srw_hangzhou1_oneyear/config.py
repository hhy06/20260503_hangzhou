"""Simulation configuration for srw_hangzhou1.

Delegates to sub-modules:
    sku.py             SKU definitions (loaded from skus.xlsx)
    bom.py             Empty stubs (BOM data in skus.xlsx + bom.xlsx)
    plant_topology.py  Node and edge definitions (auto-generated)
"""

from .sku import (
    N,
    SKUS,
)

SKUS_KEYS: set[str] = set(SKUS.keys()) if isinstance(SKUS, dict) else set(SKUS)

from .bom import (
    SAUCE_INGREDIENTS,
    POWDER_INGREDIENTS,
    VEG_INGREDIENTS,
    LINE_SKU_MAP,
    sku_bom_inputs,
)

from .plant_topology import (
    NODES,
    EDGES,
)

NUM_POWDER_LINES = 0
NUM_NOODLE_LINES = 0

MANAGEMENT = {
    "type": "excess",
    "decision_interval": 10.0,
}


_DAY_IN_MINUTES=60*24
SIM_DURATION = 365 * _DAY_IN_MINUTES


def dump_config() -> None:
    """Print all configuration data for inspection."""
    from collections.abc import Mapping, Sequence
    from .config_static_jobs import TRANSPORT_ORDERS, PRODUCTION_JOBS
    from .safe_stock import SAFE_STOCK
    from .demand import DEMAND_ORDERS

    items = {
        "N": N,
        "SKUS": SKUS,
        "NODES": NODES,
        "EDGES": EDGES,
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
