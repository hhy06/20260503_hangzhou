"""Initial stock levels for rw_hangzhou1.

Loads from data/init_stock.xlsx via :mod:`src._xlsx_loaders`.
Returns empty dict if the xlsx file is absent (no hardcoded fallback).
"""

from pathlib import Path

INIT_STOCK: dict[str, dict[str, int]] = {}

_root = Path(__file__).resolve().parents[2] / "data"
_is_path = _root / "init_stock.xlsx"

if _is_path.exists():
    from src._xlsx_loaders import load_init_stock
    INIT_STOCK = load_init_stock(_root)
