"""Bill-of-materials for srw_hangzhou1_90d.

BOM data lives in two places:
  1. skus.xlsx (SKU.bom attribute on each product SKU)
  2. bom.xlsx   (flat sku_id -> material_id + amount table)
  3. plant_topology.py (per-workstation BOM dicts, auto-generated)

This module is intentionally minimal — it provides empty stubs for
legacy imports that config.py / dump_config may reference.
"""

SAUCE_INGREDIENTS: dict = {}
POWDER_INGREDIENTS: dict = {}
VEG_INGREDIENTS: dict = {}
LINE_SKU_MAP: dict = {}


def sku_bom_inputs(i: int) -> dict:
    return {}
