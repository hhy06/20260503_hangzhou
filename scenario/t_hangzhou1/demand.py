"""Demand orders for scenario.t_hangzhou1.

Loads from data/demand.xlsx via :mod:`src._xlsx_loaders`.
"""

from pathlib import Path

DEMAND_ORDERS: list[dict] = []

_root = Path(__file__).resolve().parents[2] / "data"
_demand_path = _root / "demand.xlsx"

if _demand_path.exists():
    from src._xlsx_loaders import load_demand
    DEMAND_ORDERS = load_demand(_root)
