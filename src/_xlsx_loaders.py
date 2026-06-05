"""Per-type xlsx loading functions for scenario data.

Each function targets a single xlsx file in ``data/`` and returns the
corresponding Python data structure.  Scenarios may call any combination
of these loaders depending on which management type they use.
"""

from pathlib import Path
import sys

import pandas as pd

from src.model.sku import SKU


# ── Helpers ────────────────────────────────────────────────────────────────

def _data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data"


# ── SKU definitions + BOM ─────────────────────────────────────────────────

def load_skus_and_bom(data_dir: Path | None = None,
                      ) -> dict[str, SKU]:
    """Load SKU master data + BOM relations from *data_dir*/*.xlsx.

    Returns
    -------
    skus : dict[str, SKU]
        SKU objects with BOM data attached. pallet_size is required for each SKU.
    """
    d = data_dir or _data_dir()
    sku_path = d / "skus.xlsx"
    bom_path = d / "bom.xlsx"

    meta = pd.read_excel(sku_path, sheet_name="SKUS")
    bom = pd.read_excel(bom_path, sheet_name="BOM")

    skus: dict[str, SKU] = {}

    for _, row in meta.iterrows():
        sku_id = str(row["sku_id"])
        pallet_sz = row.get("pallet_size")
        if pallet_sz is None or pd.isna(pallet_sz):
            raise ValueError(f"SKU {sku_id} missing pallet_size in skus.xlsx")
        skus[sku_id] = SKU(
            id=sku_id,
            name=str(row.get("name", sku_id) or sku_id),
            bom_speed=float(row.get("bom_speed", 0) or 0),
            pallet_size=int(pallet_sz),
            unit=str(row.get("unit", "") or ""),
        )

    bad_refs: list[tuple[str, str]] = []
    for _, row in bom.iterrows():
        sku_id = str(row["sku_id"])
        mat_id = str(row["material_id"])
        amount = int(row["amount"])
        if sku_id not in skus:
            bad_refs.append((sku_id, mat_id))
            continue
        if mat_id not in skus:
            bad_refs.append((sku_id, mat_id))
            continue
        skus[sku_id].bom[mat_id] = amount

    n_sku = len(skus)
    n_with_bom = sum(1 for s in skus.values() if s.bom)
    n_no_bom = n_sku - n_with_bom

    print(f"[SKU] Loaded {n_sku} SKUs from Excel", file=sys.stderr)
    print(f"[SKU]   {n_with_bom} have BOM (producible)", file=sys.stderr)
    print(f"[SKU]   {n_no_bom} have no BOM (raw materials)", file=sys.stderr)
    if bad_refs:
        print(f"[SKU]   WARNING: {len(bad_refs)} BOM rows reference unknown SKUs:", file=sys.stderr)
        for sku_id, mat_id in bad_refs:
            print(f"[SKU]     {sku_id} \u2192 {mat_id} (NOT in skus.xlsx)", file=sys.stderr)
    else:
        print(f"[SKU]   All BOM material references are valid", file=sys.stderr)

    return skus


# ── Demand orders ──────────────────────────────────────────────────────────

def load_demand(data_dir: Path | None = None) -> list[dict]:
    """Load demand orders from *data_dir*/demand.xlsx.

    Returns a list of dicts with keys ``sku``, ``quantity``, ``from_node``,
    ``to_node``, ``start_time``.
    """
    d = data_dir or _data_dir()
    df = pd.read_excel(d / "demand.xlsx", sheet_name="DEMAND")

    orders: list[dict] = []
    total = 0
    prev_time: float = float("-inf")
    for _, row in df.iterrows():
        o = dict(
            sku=str(row["sku"]),
            quantity=int(row["quantity"]),
            from_node=str(row["from_node"]),
            to_node=str(row["to_node"]),
            start_time=float(row["start_time"]),
        )
        if o["start_time"] < prev_time:
            raise ValueError(
                f"demand.xlsx: start_time is not in weakly increasing order. "
                f"Row with sku={o['sku']} start_time={o['start_time']} "
                f"comes after start_time={prev_time}. "
                f"Sort the data by start_time (break ties consistently)."
            )
        orders.append(o)
        total += o["quantity"]
        prev_time = o["start_time"]

    print(f"[DEMAND] Loaded {len(orders)} orders, total {total} units", file=sys.stderr)
    return orders


# ── Safe-stock thresholds ──────────────────────────────────────────────────

def load_safe_stock(data_dir: Path | None = None) -> list[dict]:
    """Load safe-stock config from *data_dir*/safe_stock.xlsx.

    Returns a list of dicts with keys ``sku``, ``safe_stock``,
    ``replenish_qty``, ``storage``, ``source_type``, plus one of
    ``replenish_from`` / ``push_to`` / ``produce_at``.
    """
    d = data_dir or _data_dir()
    df = pd.read_excel(d / "safe_stock.xlsx", sheet_name="SAFE_STOCK")

    entries: list[dict] = []
    for _, row in df.iterrows():
        entry = dict(
            sku=str(row["sku"]),
            safe_stock=int(row["safe_stock"]),
            replenish_qty=int(row["replenish_qty"]),
            storage=str(row["storage"]),
            source_type=str(row["source_type"]),
        )
        action_key = str(row["action_key"])
        action_value = str(row["action_value"])
        entry[action_key] = action_value
        entries.append(entry)

    print(f"[SAFE_STOCK] Loaded {len(entries)} entries from Excel", file=sys.stderr)
    return entries


# ── Initial stock levels ───────────────────────────────────────────────────

def load_init_stock(data_dir: Path | None = None) -> dict[str, dict[str, int]]:
    """Load initial stock levels from *data_dir*/init_stock.xlsx.

    Returns a dict::

        {node_name: {sku: quantity, ...}, ...}
    """
    d = data_dir or _data_dir()
    df = pd.read_excel(d / "init_stock.xlsx", sheet_name="INIT_STOCK")

    result: dict[str, dict[str, int]] = {}
    for _, row in df.iterrows():
        node = str(row["node"])
        sku = str(row["sku"])
        qty = int(row["quantity"])
        result.setdefault(node, {})[sku] = qty

    n_nodes = len(result)
    n_entries = sum(len(v) for v in result.values())
    print(f"[INIT_STOCK] Loaded {n_entries} entries across {n_nodes} nodes from Excel",
          file=sys.stderr)
    return result
