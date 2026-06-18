"""Generate data/init_stock.xlsx and data/safe_stock.xlsx for rw_hangzhou1.

Algorithm:
    1. Compute FERT average daily demand from demand.xlsx.
    2. Explode through BOM (multi-level) to get HALB, ROH, VERP daily demand.
    3. Multiply by STOCK_DAY to get init_stock and safe_stock levels.
    4. Assign each SKU to its storage node and determine replenishment action.

Stock levels:
    init_stock  = ceil(daily_demand * STOCK_DAY)
    safe_stock  = ceil(daily_demand * STOCK_DAY)
    replenish_qty = ceil(daily_demand * STOCK_DAY)

Storage assignment (based on SKU type):
    FERT (17xxx)               -> fg_storage         -> produce_at workstation_X{xx}
    熟酱 HALB (15N prefix)      -> soup_storage       -> produce_at workstation_J{xx}
    酱包 HALB (1502/1507/1509)  -> sauce_wip_storage  -> produce_at workstation_{0xx}
    粉包 HALB (1501)             -> powder_wip_storage -> produce_at workstation_{F/FB/H/DF/ZL}
    菜包 HALB (1505)             -> veg_wip_storage    -> produce_at workstation_{C/DC/XC}
    ROH / VERP                  -> raw_material_storage -> replenish_from source
    lineside inputs             -> lineside_{line}    -> replenish_from appropriate pool
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEMAND_PATH = DATA_DIR / "demand.xlsx"
BOM_PATH = DATA_DIR / "bom.xlsx"
SKUS_PATH = DATA_DIR / "skus.xlsx"
TOPO_PATH = DATA_DIR / ".." / "scenario" / "rw_hangzhou1" / "plant_topology.py"

INIT_OUT = DATA_DIR / "init_stock.xlsx"
SAFE_STOCK_OUT = DATA_DIR / "safe_stock.xlsx"

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
STOCK_DAY = 14  # days of stock buffer

SIM_DAYS = 730


def ceil_or_zero(v: float) -> int:
    return math.ceil(v) if v > 0 else 0


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_demand() -> dict[str, float]:
    """Compute average daily demand per FERT SKU from demand.xlsx."""
    df = pd.read_excel(DEMAND_PATH)
    total = df.groupby("sku")["quantity"].sum()
    daily = {str(sku): float(q) / SIM_DAYS for sku, q in total.items()}
    nonzero = sum(1 for q in daily.values() if q > 0)
    print(f"[DEMAND] {len(daily)} FERT SKUs, {nonzero} with non-zero daily demand",
          file=sys.stderr)
    return daily


def load_bom() -> tuple[dict[str, dict[str, float]], set[str]]:
    """Load BOM and return (bom_dict, all_sku_ids_in_bom)."""
    df = pd.read_excel(BOM_PATH)
    bom: dict[str, dict[str, float]] = {}
    all_ids: set[str] = set()
    for _, r in df.iterrows():
        pid = str(r["sku_id"])
        mid = str(r["material_id"])
        amt = float(r["amount"])
        bom.setdefault(pid, {})[mid] = bom.get(pid, {}).get(mid, 0) + amt
        all_ids.add(pid)
        all_ids.add(mid)
    print(f"[BOM] {len(bom)} parent SKUs, {len(all_ids)} total IDs", file=sys.stderr)
    return bom, all_ids


def load_sku_set() -> set[str]:
    df = pd.read_excel(SKUS_PATH)
    ids = set(df["sku_id"].astype(str))
    print(f"[SKUS] {len(ids)} SKUs in universe", file=sys.stderr)
    return ids


def load_topology():
    """Load plant_topology.py by importing it."""
    import importlib
    sys.path.insert(0, str(DATA_DIR / ".."))
    mod = importlib.import_module("scenario.rw_hangzhou1.plant_topology")
    return mod.NODES, mod.EDGES


# ---------------------------------------------------------------------------
# BOM explosion
# ---------------------------------------------------------------------------

def explode_demand(fert_daily: dict[str, float], bombom, sku_set: set,
                   max_depth: int = 10) -> dict[str, float]:
    """Propagate FERT demand through BOM to get HALB, ROH, VERP demand.

    Generation-by-generation expansion: each generation multiplies parent
    demand by child BOM amounts. Handles multi-level HALB chains.
    """
    demand: dict[str, float] = dict(fert_daily)
    current_gen: dict[str, float] = dict(fert_daily)

    for depth in range(max_depth):
        if not current_gen:
            break
        next_gen: dict[str, float] = {}
        for parent, parent_daily in current_gen.items():
            if parent_daily <= 0:
                continue
            children = bom.get(parent, {})
            for child, amt in children.items():
                if child not in sku_set:
                    continue
                child_added = parent_daily * amt
                demand[child] = demand.get(child, 0) + child_added
                if child in bom:
                    next_gen[child] = next_gen.get(child, 0) + child_added
        current_gen = next_gen

    return demand


# ---------------------------------------------------------------------------
# SKU classification
# ---------------------------------------------------------------------------

def classify_sku(sku_id: str, bom: dict) -> str:
    """Return 'fg', 'wip', or 'raw'."""
    if sku_id.startswith("17"):
        return "fg"
    if sku_id in bom:
        return "wip"
    return "raw"


def source_type_for(sku_id: str, bom: dict) -> str:
    """Return source_type string for safe_stock."""
    if sku_id.startswith("17"):
        return "fg"
    if sku_id in bom:
        return "wip"
    return "raw_material"


def pool_for_wip(sku_id: str) -> str:
    """Determine WIP pool storage node for a HALB SKU."""
    if sku_id.startswith("15N"):
        return "soup_storage"
    if sku_id.startswith("1502") or sku_id.startswith("1507") or sku_id.startswith("1509"):
        return "sauce_wip_storage"
    if sku_id.startswith("1501"):
        return "powder_wip_storage"
    if sku_id.startswith("1505"):
        return "veg_wip_storage"
    return "raw_material_storage"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global bom
    fert_daily = load_demand()
    bom, bom_ids = load_bom()
    sku_set = load_sku_set()
    nodes, edges = load_topology()

    all_daily = explode_demand(fert_daily, bom, sku_set)
    print(f"[EXPLODE] {len(all_daily)} SKUs with daily demand", file=sys.stderr)

    # Build producing-line mapping: output_sku -> workstation_name
    sku_to_line: dict[str, str] = {}
    for name, cfg in nodes.items():
        if cfg["type"] == "production":
            for out_sku in cfg.get("bom", {}):
                sku_to_line[out_sku] = name

    # Build lineside input mapping: lineside_node -> set of input SKUs
    lineside_inputs: dict[str, dict[str, set[str]]] = {}
    for name, cfg in nodes.items():
        if cfg["type"] == "production":
            lid = name.replace("workstation_", "")
            lineside_node = f"lineside_{lid}"
            inputs = {}
            for out_sku, entry in cfg.get("bom", {}).items():
                for inp_sku in entry.get("inputs", {}):
                    inputs.setdefault(inp_sku, set()).add(out_sku)
            if lineside_node not in lineside_inputs:
                lineside_inputs[lineside_node] = {}
            for inp_sku in inputs:
                lineside_inputs[lineside_node].setdefault(inp_sku, set()).update(inputs[inp_sku])

    # -------------------------------------------------------------------
    # init_stock.xlsx: (node, sku, quantity)
    # -------------------------------------------------------------------
    init_rows: list[dict] = []

    for sku_id, daily in all_daily.items():
        if daily <= 0:
            continue
        stock = ceil_or_zero(daily * STOCK_DAY)
        if stock == 0:
            continue

        cls = classify_sku(sku_id, bom)

        if cls == "fg":
            init_rows.append({"node": "fg_storage", "sku": sku_id, "quantity": stock})
        elif cls == "wip":
            pool = pool_for_wip(sku_id)
            init_rows.append({"node": pool, "sku": sku_id, "quantity": stock})
        else:
            init_rows.append({"node": "raw_material_storage", "sku": sku_id, "quantity": stock})

    for lineside_node, inp_map in lineside_inputs.items():
        for inp_sku in inp_map:
            daily = all_daily.get(inp_sku, 0)
            if daily <= 0:
                continue
            stock = ceil_or_zero(daily * STOCK_DAY)
            if stock == 0:
                continue
            existing = any(
                r["node"] == lineside_node and r["sku"] == inp_sku for r in init_rows
            )
            if not existing:
                init_rows.append(
                    {"node": lineside_node, "sku": inp_sku, "quantity": stock}
                )

    init_df = pd.DataFrame(init_rows, columns=["node", "sku", "quantity"])

    # -------------------------------------------------------------------
    # safe_stock.xlsx: (sku, safe_stock, replenish_qty, storage, source_type,
    #                    action_key, action_value)
    # -------------------------------------------------------------------
    safe_rows: list[dict] = []

    for sku_id, daily in all_daily.items():
        if daily <= 0:
            continue
        ss = ceil_or_zero(daily * STOCK_DAY)
        if ss == 0:
            continue
        rq = ss
        cls = classify_sku(sku_id, bom)
        src_type = source_type_for(sku_id, bom)

        if cls == "fg":
            line = sku_to_line.get(sku_id)
            if line:
                safe_rows.append({
                    "sku": sku_id,
                    "safe_stock": ss,
                    "replenish_qty": rq,
                    "storage": "fg_storage",
                    "source_type": src_type,
                    "action_key": "produce_at",
                    "action_value": line,
                })
            else:
                print(f"[WARN] FERT {sku_id} has no producing line, skipping safe_stock",
                      file=sys.stderr)
        elif cls == "wip":
            pool = pool_for_wip(sku_id)
            line = sku_to_line.get(sku_id)
            if line:
                safe_rows.append({
                    "sku": sku_id,
                    "safe_stock": ss,
                    "replenish_qty": rq,
                    "storage": pool,
                    "source_type": src_type,
                    "action_key": "produce_at",
                    "action_value": line,
                })
            else:
                print(f"[WARN] WIP {sku_id} has no producing line, skipping safe_stock",
                      file=sys.stderr)
        else:
            safe_rows.append({
                "sku": sku_id,
                "safe_stock": ss,
                "replenish_qty": rq,
                "storage": "raw_material_storage",
                "source_type": src_type,
                "action_key": "replenish_from",
                "action_value": "source",
            })

    for lineside_node, inp_map in lineside_inputs.items():
        for inp_sku in inp_map:
            daily = all_daily.get(inp_sku, 0)
            if daily <= 0:
                continue
            ss = ceil_or_zero(daily * STOCK_DAY)
            if ss == 0:
                continue
            rq = ss
            src_type = source_type_for(inp_sku, bom)
            cls = classify_sku(inp_sku, bom)

            if cls == "wip":
                upstream_pool = pool_for_wip(inp_sku)
            else:
                upstream_pool = "raw_material_storage"

            existing = any(
                r["sku"] == inp_sku and r["storage"] == lineside_node
                for r in safe_rows
            )
            if not existing:
                safe_rows.append({
                    "sku": inp_sku,
                    "safe_stock": ss,
                    "replenish_qty": rq,
                    "storage": lineside_node,
                    "source_type": src_type,
                    "action_key": "replenish_from",
                    "action_value": upstream_pool,
                })

    safe_df = pd.DataFrame(safe_rows, columns=[
        "sku", "safe_stock", "replenish_qty", "storage",
        "source_type", "action_key", "action_value",
    ])

    INIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(INIT_OUT, engine="openpyxl") as writer:
        init_df.to_excel(writer, sheet_name="INIT_STOCK", index=False)

    with pd.ExcelWriter(SAFE_STOCK_OUT, engine="openpyxl") as writer:
        safe_df.to_excel(writer, sheet_name="SAFE_STOCK", index=False)

    print(f"\n[INIT_STOCK] Wrote {INIT_OUT}", file=sys.stderr)
    print(f"[INIT_STOCK]   {len(init_df)} rows", file=sys.stderr)
    by_node = init_df.groupby("node").size()
    for node, n in sorted(by_node.items(), key=lambda x: -x[1])[:10]:
        print(f"[INIT_STOCK]   {node}: {n}", file=sys.stderr)
    if len(by_node) > 10:
        print(f"[INIT_STOCK]   ... +{len(by_node) - 10} more nodes", file=sys.stderr)

    print(f"\n[SAFE_STOCK] Wrote {SAFE_STOCK_OUT}", file=sys.stderr)
    print(f"[SAFE_STOCK]   {len(safe_df)} rows", file=sys.stderr)
    by_storage = safe_df.groupby("storage").size()
    for st, n in sorted(by_storage.items(), key=lambda x: -x[1])[:10]:
        print(f"[SAFE_STOCK]   {st}: {n}", file=sys.stderr)
    if len(by_storage) > 10:
        print(f"[SAFE_STOCK]   ... +{len(by_storage) - 10} more storages", file=sys.stderr)
    by_action = safe_df.groupby("action_key").size()
    for act, n in sorted(by_action.items(), key=lambda x: -x[1]):
        print(f"[SAFE_STOCK]   {act}: {n}", file=sys.stderr)


if __name__ == "__main__":
    main()
