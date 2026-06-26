"""Generate bom.xlsx for scenario srw_hangzhou1_90d.

Sources:
    ~/transf/temp/masterkong_large_康师傅/simple_bom_by_product.csv
    ~/transf/temp/masterkong_large_康师傅/key_sku_share_2025H2.csv  (to seed FG set)

Logic:
    1. Compute the same 2-layer SKU universe as _generate_skus.py.
    2. For every BOM row in simple_bom_by_product.csv where BOTH product and material
       are in our SKU universe, emit a row into bom.xlsx.
    3. Validate all sku_id and material_id references against skus.xlsx.

Simple BOM is flatter than the original: sauce packets (酱包) are now produced
directly from ROH+VERP (no intermediate 熟酱 step). The FERT BOM remains
2-layer: FG → HALB(sauce/powder/veg packets + packaging) → ROH/VERP.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SRC_DIR = Path.home() / "transf" / "temp" / "masterkong_large_康师傅"
SHARE_CSV = SRC_DIR / "key_sku_share_2025H2.csv"
BOM_CSV = SRC_DIR / "simple_bom_by_product.csv"

OUT_PATH = Path(__file__).resolve().parents[0] / "bom.xlsx"
SKUS_PATH = Path(__file__).resolve().parents[0] / "skus.xlsx"


def load_fg_ids() -> set[str]:
    df = pd.read_csv(SHARE_CSV)
    ids = set(df["物料"].astype(str))
    print(f"[FG] {len(ids)} FG SKUs", file=sys.stderr)
    return ids


def load_bom() -> pd.DataFrame:
    df = pd.read_csv(BOM_CSV, encoding='utf-8-sig')
    df = df.rename(columns={
        "产品物料号": "prod_id",
        "投入物料号": "mat_id",
        "单位消耗量": "unit_consumption",
        "投入物料类型": "mat_type",
        "产品类型": "prod_type",
    })
    df["prod_id"] = df["prod_id"].astype(str)
    df["mat_id"] = df["mat_id"].astype(str)
    df["unit_consumption"] = pd.to_numeric(df["unit_consumption"], errors="coerce").fillna(0.0)
    print(f"[BOM] Loaded {len(df)} BOM rows", file=sys.stderr)
    return df


def collect_sku_universe(fg_ids: set[str], bom: pd.DataFrame) -> set[str]:
    """Collect all SKUs reachable from FG set through BOM graph (2-layer walk)."""
    # prod_id -> materials list (only keep relevant types)
    bom_by_prod: dict[str, list[dict]] = {}
    for _, row in bom.iterrows():
        bom_by_prod.setdefault(row["prod_id"], []).append({
            "mat_id": row["mat_id"],
            "mat_type": row["mat_type"],
        })

    universe: set[str] = set()
    visited_halb: set[str] = set()

    def walk_halb(halb_id: str) -> None:
        if halb_id in visited_halb:
            return
        visited_halb.add(halb_id)
        universe.add(halb_id)
        for r in bom_by_prod.get(halb_id, []):
            mid = r["mat_id"]
            mtype = r["mat_type"]
            universe.add(mid)
            if mtype == "HALB":
                walk_halb(mid)

    for fg in fg_ids:
        universe.add(fg)
        for r in bom_by_prod.get(fg, []):
            mid = r["mat_id"]
            universe.add(mid)
            if r["mat_type"] == "HALB":
                walk_halb(mid)

    return universe


def main() -> None:
    fg_ids = load_fg_ids()
    bom = load_bom()
    universe = collect_sku_universe(fg_ids, bom)
    print(f"[COLLECT] SKU universe: {len(universe)}", file=sys.stderr)

    # Filter BOM rows: both prod and mat in universe
    mask = bom["prod_id"].isin(universe) & bom["mat_id"].isin(universe)
    filtered = bom[mask].copy()

    # Deduplicate: keep max unit_consumption per (prod_id, mat_id) pair
    # (same product + material from multiple production runs should collapse)
    if filtered.duplicated(subset=["prod_id", "mat_id"]).any():
        n_dup = filtered.duplicated(subset=["prod_id", "mat_id"]).sum()
        print(f"[BOM] Deduplicating {n_dup} duplicate (prod,mat) pairs (keeping mean)", file=sys.stderr)
        filtered = (
            filtered.groupby(["prod_id", "mat_id"], as_index=False)["unit_consumption"]
            .mean()
        )

    out = filtered[["prod_id", "mat_id", "unit_consumption"]].rename(columns={
        "prod_id": "sku_id",
        "mat_id": "material_id",
        "unit_consumption": "amount",
    }).sort_values(["sku_id", "material_id"]).reset_index(drop=True)

    # Validate against skus.xlsx if it exists
    if SKUS_PATH.exists():
        skus_df = pd.read_excel(SKUS_PATH, sheet_name="SKUS")
        sku_set = set(skus_df["sku_id"].astype(str))
        bad_products = set(out["sku_id"]) - sku_set
        bad_materials = set(out["material_id"]) - sku_set
        if bad_products:
            print(f"[WARN] {len(bad_products)} BOM sku_ids not in skus.xlsx: {list(bad_products)[:5]}...", file=sys.stderr)
        if bad_materials:
            print(f"[WARN] {len(bad_materials)} BOM material_ids not in skus.xlsx: {list(bad_materials)[:5]}...", file=sys.stderr)
        if not bad_products and not bad_materials:
            print(f"[BOM] All references validated against skus.xlsx", file=sys.stderr)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        out.to_excel(writer, sheet_name="BOM", index=False)

    print(f"\n[BOM] Wrote {OUT_PATH}", file=sys.stderr)
    print(f"[BOM]   {len(out)} BOM rows", file=sys.stderr)
    n_products = out["sku_id"].nunique()
    n_materials = out["material_id"].nunique()
    print(f"[BOM]   {n_products} products x {n_materials} unique materials", file=sys.stderr)
    avg_inputs = len(out) / n_products if n_products else 0
    print(f"[BOM]   Avg {avg_inputs:.1f} inputs per product", file=sys.stderr)


if __name__ == "__main__":
    main()
