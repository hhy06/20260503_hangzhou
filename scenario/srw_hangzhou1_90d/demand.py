"""Demand orders for scenario.srw_hangzhou1_90d.

Loads from demand.xlsx (local to this scenario) via :mod:`src._xlsx_loaders`.
"""

from pathlib import Path

DEMAND_ORDERS: list[dict] = []

_root = Path(__file__).resolve().parents[0]
_demand_path = _root / "demand.xlsx"

if _demand_path.exists():
    from src._xlsx_loaders import load_demand
    DEMAND_ORDERS = load_demand(_demand_path)
