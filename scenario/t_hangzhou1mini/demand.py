"""Demand orders for scenario.t_hangzhou1mini.

Loads from data/demand.xlsx when available, otherwise uses hardcoded fallback.
"""
from pathlib import Path

import pandas as pd

DEMAND_ORDERS: list[dict] = []

_root = Path(__file__).resolve().parents[2]
_demand_path = _root / "data" / "demand.xlsx"

if _demand_path.exists():
    df = pd.read_excel(_demand_path, sheet_name="DEMAND")
    total = 0
    for _, row in df.iterrows():
        d = dict(
            sku=str(row["sku"]),
            quantity=int(row["quantity"]),
            from_node=str(row["from_node"]),
            to_node=str(row["to_node"]),
            start_time=float(row["start_time"]),
        )
        DEMAND_ORDERS.append(d)
        total += d["quantity"]
    print(f"[DEMAND] Loaded {len(DEMAND_ORDERS)} orders, total {total} units", file=__import__("sys").stderr)
else:
    DEMAND_ORDERS.append(dict(
        sku="SKU_1",
        quantity=5000,
        from_node="fg_storage",
        to_node="sink",
        start_time=10000,
    ))