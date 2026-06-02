"""Demand orders for scenario.t_hangzhou1mini.

Loads from data/demand.xlsx via :mod:`src._xlsx_loaders`.

Falls back to hardcoded data when the xlsx file is absent.
"""
from pathlib import Path

DEMAND_ORDERS: list[dict] = []

_root = Path(__file__).resolve().parents[2] / "data"
_demand_path = _root / "demand.xlsx"

if _demand_path.exists():
    from src._xlsx_loaders import load_demand
    DEMAND_ORDERS = load_demand(_root)
else:
    DEMAND_ORDERS.append(dict(
        sku="SKU_1",
        quantity=5000,
        from_node="fg_storage",
        to_node="sink",
        start_time=10000,
    ))