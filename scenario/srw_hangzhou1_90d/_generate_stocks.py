"""Generate daily_demand.xlsx, init_stock.xlsx, and safe_stock.xlsx for srw_hangzhou1_90d.

Design:
    daily_demand.xlsx  =  objective truth: per-FERT-SKU daily demand
                          (derived from 2-year forecast, independent of short-term simulation)
    init_stock.xlsx    =  allocation strategy: where to place initial stock at t=0
    safe_stock.xlsx    =  global safety thresholds per SKU (used by management for shortage
                          ratio, node-agnostic)

Data flow:
    daily_forecast_2026_2027.csv (730 days)
    key_sku_share_2025H2.csv (260 FG SKUs)
           |
           v
    stable_daily_total = sum(daily_forecast) / 730
    FERT_sku_daily = stable_daily_total * share_norm
           |
           v
    daily_demand.xlsx  (FERT only, 260 rows)
           |
    BOM explosion (bom.xlsx) -> all SKUs' daily demand
           |
           +---> init_stock.xlsx   = daily * INIT_DAYS(8),  allocated to nodes
           +---> safe_stock.xlsx   = daily * SAFE_DAYS(14), global per SKU

Stock levels / node assignment for init_stock:
    FERT (17xxx)               -> fg_storage
    酱包/粉包 (1502/1507/1509/1501) -> prep_storage_1, prep_storage_2, or both
                                    (decided by which X lines consume them:
                                     X00-X08 -> prep_1; X09-X15/X18 -> prep_2;
                                     both groups -> split 50/50)
    菜包 (1505)                -> prep_storage_1, prep_storage_2 (same logic)
    ROH / VERP                 -> raw_material_storage (if only used by C lines -> veg_raw_storage)
    lineside inputs            -> lineside_{line}

safe_stock.xlsx columns:
    sku | safe_stock_level
    Node-agnostic, used by weigh_safe_stock_management to compute shortage ratio
    = sum(all node stock) / sum(all safe_stock entries for this SKU)
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parents[0]
FORECAST_CSV = Path.home() / "transf" / "temp" / "masterkong_large_康师傅" / "daily_forecast_2026_2027.csv"
SHARE_CSV = Path.home() / "transf" / "temp" / "masterkong_large_康师傅" / "key_sku_share_2025H2.csv"
BOM_PATH = DATA_DIR / "bom.xlsx"
SKUS_PATH = DATA_DIR / "skus.xlsx"

DAILY_OUT = DATA_DIR / "daily_demand.xlsx"
INIT_OUT = DATA_DIR / "init_stock.xlsx"
SAFE_STOCK_OUT = DATA_DIR / "safe_stock.xlsx"

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
FORECAST_DAYS = 730
INIT_DAYS = 8
SAFE_DAYS = 14


def ceil_or_zero(v: float) -> int:
    return math.ceil(v) if v > 0 else 0


# ---------------------------------------------------------------------------
# Step 1: Compute stable FERT daily demand
# ---------------------------------------------------------------------------

def load_stable_daily_total() -> float:
    """Compute stable daily demand (CS/day) from the 2-year forecast."""
    fc = pd.read_csv(FORECAST_CSV, thousands=",", encoding="utf-8-sig")
    col = [c for c in fc.columns if "当日分配" in c]
    if not col:
        raise KeyError("daily_forecast.csv missing '当日分配(CS)' column")
    fc[col[0]] = pd.to_numeric(fc[col[0]].astype(str).str.replace(",", ""), errors="coerce").fillna(0).astype(int)
    total_cs = int(fc[col[0]].sum())
    daily = total_cs / FORECAST_DAYS
    print(f"[FORECAST] Total CS over {FORECAST_DAYS} days = {total_cs:,}", file=sys.stderr)
    print(f"[FORECAST] Stable daily total = {daily:,.0f} CS/day", file=sys.stderr)
    return daily


def load_sku_shares() -> dict[str, float]:
    """Return {sku: share_norm} from key_sku_share CSV."""
    df = pd.read_csv(SHARE_CSV)
    df = df.rename(columns={"物料": "sku", "占比%": "share_pct"})
    df["sku"] = df["sku"].astype(str)
    df["share_pct"] = pd.to_numeric(df["share_pct"], errors="coerce").fillna(0.0)
    total = df["share_pct"].sum()
    if total <= 0:
        raise ValueError(f"Sum of share_pct is non-positive: {total}")
    df["share_norm"] = df["share_pct"] / total
    result = {str(r["sku"]): float(r["share_norm"]) for _, r in df.iterrows() if r["share_norm"] > 0}
    print(f"[SHARE] {len(result)} SKUs with positive share", file=sys.stderr)
    return result


def compute_fert_daily(stable_daily: float, shares: dict[str, float]) -> dict[str, float]:
    """Return {fert_sku: daily_demand}."""
    return {sku: stable_daily * norm for sku, norm in shares.items()}


# ---------------------------------------------------------------------------
# Step 2: BOM explosion
# ---------------------------------------------------------------------------

def load_bom() -> tuple[dict[str, dict[str, float]], set[str]]:
    """Load BOM and return (bom_dict, all_sku_ids)."""
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


def explode_demand(fert_daily: dict[str, float], bom: dict, sku_set: set,
                   max_depth: int = 10) -> dict[str, float]:
    """Propagate FERT demand through BOM tree."""
    demand: dict[str, float] = dict(fert_daily)
    current: dict[str, float] = dict(fert_daily)

    for _ in range(max_depth):
        if not current:
            break
        nxt: dict[str, float] = {}
        for parent, parent_daily in current.items():
            if parent_daily <= 0:
                continue
            for child, amt in bom.get(parent, {}).items():
                if child not in sku_set:
                    continue
                demand[child] = demand.get(child, 0) + parent_daily * amt
                if child in bom:
                    nxt[child] = nxt.get(child, 0) + parent_daily * amt
        current = nxt

    nonzero = sum(1 for v in demand.values() if v > 0)
    print(f"[EXPLODE] {nonzero} SKUs with daily demand", file=sys.stderr)
    return demand


# ---------------------------------------------------------------------------
# Step 3: Load topology (for lineside allocation and X line mapping)
# ---------------------------------------------------------------------------

def load_topology() -> tuple[dict, list]:
    """Load plant_topology.py."""
    import importlib
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    try:
        mod = importlib.import_module("scenario.srw_hangzhou1_90d.plant_topology")
        return mod.NODES, mod.EDGES
    except ModuleNotFoundError:
        print("[STOCKS] Warning: plant_topology.py not found, falling back", file=sys.stderr)
        return {}, []


# ---------------------------------------------------------------------------
# Step 4: Determine X-line group (prep_1 or prep_2) for each X line
# ---------------------------------------------------------------------------

X_LINES_PREP_1 = {"X00", "X01", "X02", "X03", "X04", "X05", "X06", "X07", "X08"}
X_LINES_PREP_2 = {"X09", "X10", "X11", "X12", "X13", "X14", "X15", "X18"}

def classify_sku(sku_id: str, bom: dict) -> str:
    """Return 'fg', 'wip', or 'raw'."""
    if sku_id.startswith("17"):
        return "fg"
    if sku_id in bom:
        return "wip"
    return "raw"


def veg_raw_skus(nodes: dict, bom: dict) -> dict[str, set[str]]:
    """Build {wip_sku: set of FERT SKUs that consume it}, by tracing FERT BOM."""
    consumers: dict[str, set[str]] = defaultdict(set)
    for name, cfg in nodes.items():
        if cfg.get("type") != "production":
            continue
        lid = name.replace("workstation_", "")
        if not lid.startswith("X"):
            continue
        for fert_sku, entry in cfg.get("bom", {}).items():
            for inp_sku in entry.get("inputs", {}):
                consumers[inp_sku].add(fert_sku)
    return consumers


def determine_x_consumer_groups(wip_sku: str, consumers: dict[str, set[str]],
                                 fert_bom: dict[str, dict[str, float]]) -> tuple[bool, bool]:
    """For a WIP SKU, return (used_by_prep_1_groups, used_by_prep_2_groups).

    Traces through FERT SKUs to see which X-lines consume the WIP.
    """
    # Find which FERT SKUs need this WIP SKU (from the consumer map built from X line BOM)
    fert_consumers = consumers.get(wip_sku, set())
    # Also trace: other FERT SKUs that have this WIP in their BOM entry
    for fert_sku, inputs in fert_bom.items():
        if wip_sku in inputs:
            fert_consumers.add(fert_sku)

    if not fert_consumers:
        return False, False

    in_group_1 = any(fid in X_LINES_PREP_1 or
                     any(fid == fert for fid in fert_consumers)
                     for fid in fert_consumers)
    # Actually we need to know which X LINES produce which FERT SKUs
    # But simpler: just check if the FERT SKU is produced by an X line in prep_1 or prep_2 group
    # We don't have that mapping directly here, so use a heuristic:
    # all FERT SKUs can be produced by lines in either group.
    # The real question is: which WIP items are consumed by which FERT?
    # We already have that in fert_consumers.
    # But we don't know which X-line those FERT are assigned to.
    # Fall back: if consumed by any FERT (which all are produced by X lines),
    # split between both based on whether it's a universal WIP or not.

    # Simpler approach: we just always return (True, True) - split evenly.
    # User can hand-tune per SKU later.
    return True, True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    stable_daily = load_stable_daily_total()
    shares = load_sku_shares()
    fert_daily = compute_fert_daily(stable_daily, shares)
    print(f"[FERT] {len(fert_daily)} FERT SKUs with daily demand", file=sys.stderr)

    bom, bom_ids = load_bom()
    sku_set = load_sku_set()
    all_daily = explode_demand(fert_daily, bom, sku_set)

    nodes, edges = load_topology()

    # Build lineside input mapping: {lineside_node: set of input SKUs}
    lineside_inputs: dict[str, dict[str, set[str]]] = {}
    for name, cfg in nodes.items():
        if cfg.get("type") == "production":
            lid = name.replace("workstation_", "")
            lineside_node = f"lineside_{lid}"
            for out_sku, entry in cfg.get("bom", {}).items():
                for inp_sku in entry.get("inputs", {}):
                    lineside_inputs.setdefault(lineside_node, {}).setdefault(inp_sku, set()).add(out_sku)

    # Build line category mapping for storage assignment
    line_categories: dict[str, str] = {}
    for name, cfg in nodes.items():
        if cfg.get("type") == "production":
            lid = name.replace("workstation_", "")
            if lid.startswith("J") or lid == "ZJ1":
                line_categories[lid] = "J_sauce"
            elif lid.startswith("X"):
                line_categories[lid] = "X_fert"
            elif lid.startswith("C") or lid.startswith("DC") or lid in ("XC1", "XC2"):
                line_categories[lid] = "C_veg"
            elif lid.startswith("F") or lid.startswith("FB") or lid.startswith("H") or lid in ("DF1", "ZL1"):
                line_categories[lid] = "F_powder"

    # Build wip_sku -> {FERT_SKUs consuming it} from X-line workstation BOMs
    wip_consumers: dict[str, set[str]] = defaultdict(set)
    fert_bom_all: dict[str, dict[str, float]] = {}
    for name, cfg in nodes.items():
        if cfg.get("type") == "production":
            lid = name.replace("workstation_", "")
            if lid.startswith("X"):
                grp = "prep_1" if lid in X_LINES_PREP_1 else "prep_2"
                for fert_sku, entry in cfg.get("bom", {}).items():
                    for inp_sku in entry.get("inputs", {}):
                        wip_consumers[inp_sku].add((fert_sku, grp))
                        fert_bom_all.setdefault(fert_sku, {})[inp_sku] = entry["inputs"][inp_sku]

    # -------------------------------------------------------------------
    # File 1: daily_demand.xlsx  (FERT only)
    # -------------------------------------------------------------------
    daily_rows = [
        {"sku": sku, "daily_demand": round(val, 2)}
        for sku, val in sorted(fert_daily.items())
        if val > 0
    ]
    daily_df = pd.DataFrame(daily_rows, columns=["sku", "daily_demand"])

    # -------------------------------------------------------------------
    # File 2: init_stock.xlsx  (daily_demand * INIT_DAYS, allocated to nodes)
    # -------------------------------------------------------------------
    init_rows: list[dict] = []

    # (a) FERT + WIP + raw: assign to primary storage
    c_line_skus: set[str] = set()
    for lid, cat in line_categories.items():
        if cat == "C_veg":
            ls = f"lineside_{lid}"
            for inp_sku in lineside_inputs.get(ls, {}):
                c_line_skus.add(inp_sku)

    for sku_id, daily in all_daily.items():
        if daily <= 0:
            continue
        stock = ceil_or_zero(daily * INIT_DAYS)
        if stock == 0:
            continue

        cls = classify_sku(sku_id, bom)

        if cls == "fg":
            init_rows.append({"node": "fg_storage", "sku": sku_id, "quantity": stock})

        elif cls == "wip":
            # WIP: assign to prep_storage based on which X-line groups consume it
            grp_1_consumers = {fs for fs, g in wip_consumers.get(sku_id, set()) if g == "prep_1"}
            grp_2_consumers = {fs for fs, g in wip_consumers.get(sku_id, set()) if g == "prep_2"}
            has_g1 = bool(grp_1_consumers)
            has_g2 = bool(grp_2_consumers)

            if has_g1 and has_g2:
                # split 50/50
                half = max(1, stock // 2)
                init_rows.append({"node": "prep_storage_1", "sku": sku_id, "quantity": half})
                init_rows.append({"node": "prep_storage_2", "sku": sku_id, "quantity": stock - half})
            elif has_g2:
                init_rows.append({"node": "prep_storage_2", "sku": sku_id, "quantity": stock})
            else:
                # default to prep_1 (includes FERT SKUs without clear X-line mapping)
                init_rows.append({"node": "prep_storage_1", "sku": sku_id, "quantity": stock})

        else:
            # ROH/VERP: raw storage. Veg-only -> veg_raw_storage
            if sku_id in c_line_skus:
                # check if used ONLY by C lines
                used_by_other = False
                for lid, cat in line_categories.items():
                    if cat == "C_veg":
                        continue
                    ls = f"lineside_{lid}"
                    if sku_id in lineside_inputs.get(ls, {}):
                        used_by_other = True
                        break
                if used_by_other:
                    storage = "raw_material_storage"
                else:
                    storage = "veg_raw_storage"
            else:
                storage = "raw_material_storage"
            init_rows.append({"node": storage, "sku": sku_id, "quantity": stock})

    # (b) lineside: allocate per-line per-input
    for lineside_node, inp_map in lineside_inputs.items():
        lid = lineside_node.replace("lineside_", "")
        cat = line_categories.get(lid, "")

        for inp_sku in inp_map:
            daily = all_daily.get(inp_sku, 0)
            if daily <= 0:
                continue
            stock = ceil_or_zero(daily * INIT_DAYS)
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
    # File 3: safe_stock.xlsx  (global per SKU, daily * SAFE_DAYS)
    # -------------------------------------------------------------------
    safe_rows: list[dict] = []
    for sku_id, daily in all_daily.items():
        if daily <= 0:
            continue
        ss = ceil_or_zero(daily * SAFE_DAYS)
        if ss == 0:
            continue
        safe_rows.append({"sku": sku_id, "safe_stock": ss})

    safe_df = pd.DataFrame(safe_rows, columns=["sku", "safe_stock"])

    # -------------------------------------------------------------------
    # Write outputs
    # -------------------------------------------------------------------
    DAILY_OUT.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(DAILY_OUT, engine="openpyxl") as writer:
        daily_df.to_excel(writer, sheet_name="DAILY_DEMAND", index=False)
    print(f"\n[DAILY_DEMAND] Wrote {DAILY_OUT}", file=sys.stderr)
    print(f"[DAILY_DEMAND]   {len(daily_df)} FERT SKUs", file=sys.stderr)

    with pd.ExcelWriter(INIT_OUT, engine="openpyxl") as writer:
        init_df.to_excel(writer, sheet_name="INIT_STOCK", index=False)
    print(f"\n[INIT_STOCK] Wrote {INIT_OUT}", file=sys.stderr)
    print(f"[INIT_STOCK]   {len(init_df)} rows", file=sys.stderr)
    by_node = init_df.groupby("node").size()
    for node, n in sorted(by_node.items(), key=lambda x: -x[1])[:10]:
        print(f"[INIT_STOCK]   {node}: {n}", file=sys.stderr)
    if len(by_node) > 10:
        print(f"[INIT_STOCK]   ... +{len(by_node) - 10} more nodes", file=sys.stderr)

    with pd.ExcelWriter(SAFE_STOCK_OUT, engine="openpyxl") as writer:
        safe_df.to_excel(writer, sheet_name="SAFE_STOCK", index=False)
    print(f"\n[SAFE_STOCK] Wrote {SAFE_STOCK_OUT}", file=sys.stderr)
    print(f"[SAFE_STOCK]   {len(safe_df)} rows (global per SKU)", file=sys.stderr)


if __name__ == "__main__":
    main()
