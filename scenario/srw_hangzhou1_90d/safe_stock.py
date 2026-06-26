"""Safe-stock configuration for scenario.srw_hangzhou1_90d.

Loads from safe_stock.xlsx (local to this scenario) via :mod:`src._xlsx_loaders`.
Returns empty list if the xlsx file is absent (no hardcoded fallback).
"""

from pathlib import Path

SAFE_STOCK: list[dict] = []

_root = Path(__file__).resolve().parents[0]
_ss_path = _root / "safe_stock.xlsx"

if _ss_path.exists():
    from src._xlsx_loaders import load_safe_stock
    SAFE_STOCK = load_safe_stock(_root)
