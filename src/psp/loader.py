"""Load scenario data from existing xlsx files and topology module."""

import importlib
import sys
from pathlib import Path

import pandas as pd

from src.model.sku import SKU


def load_skus_and_bom(data_dir: Path) -> dict[str, SKU]:
    sku_path = data_dir / "skus.xlsx"
    bom_path = data_dir / "bom.xlsx"
    meta = pd.read_excel(sku_path, sheet_name="SKUS")
    bom = pd.read_excel(bom_path, sheet_name="BOM")
    skus: dict[str, SKU] = {}
    for _, row in meta.iterrows():
        sku_id = str(row["sku_id"])
        pallet_sz = row.get("pallet_size")
        if pallet_sz is None or pd.isna(pallet_sz):
            raise ValueError(f"SKU {sku_id} missing pallet_size")
        skus[sku_id] = SKU(
            id=sku_id,
            name=str(row.get("name", sku_id) or sku_id),
            bom_speed=float(row.get("bom_speed", 0) or 0),
            pallet_size=int(pallet_sz),
            unit=str(row.get("unit", "") or ""),
        )
    for _, row in bom.iterrows():
        sku_id = str(row["sku_id"])
        mat_id = str(row["material_id"])
        amount = float(row["amount"])
        if sku_id in skus and mat_id in skus:
            skus[sku_id].bom[mat_id] = amount
    print(f"[LOAD] {len(skus)} SKUs loaded")
    return skus


def load_demand(data_dir: Path) -> list[dict]:
    xlsx_path = data_dir / "demand.xlsx"
    df = pd.read_excel(xlsx_path, sheet_name="DEMAND")
    orders: list[dict] = []
    for _, row in df.iterrows():
        orders.append(dict(
            sku=str(row["sku"]),
            quantity=int(row["quantity"]),
            start_time=float(row["start_time"]),
        ))
    print(f"[LOAD] {len(orders)} demand rows loaded")
    return orders


def load_init_stock(data_dir: Path) -> dict[str, dict[str, int]]:
    xlsx_path = data_dir / "init_stock.xlsx"
    df = pd.read_excel(xlsx_path, sheet_name="INIT_STOCK")
    result: dict[str, dict[str, int]] = {}
    for _, row in df.iterrows():
        node = str(row["node"])
        sku = str(row["sku"])
        qty = int(row["quantity"])
        result.setdefault(node, {})[sku] = qty
    return result


def load_topology(project_root: Path, scenario_name: str) -> tuple[dict, list]:
    sys.path.insert(0, str(project_root))
    topo = importlib.import_module(f"scenario.{scenario_name}.plant_topology")
    return topo.NODES, topo.EDGES
