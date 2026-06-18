"""Generate data/skus.xlsx for scenario rw_hangzhou1.

Sources:
    ~/transf/temp/masterkong_large_康师傅/key_sku_share_2025H2.csv   (260 FG SKUs)
    ~/transf/temp/masterkong_large_康师傅/bom_by_product.csv         (all BOM rows)
    ~/transf/temp/masterkong_large_康师傅/SKU_Classification_20260527_sku分类明细.csv  (pack size)

Logic:
    1. Seed 260 FG SKUs.
    2. Walk BOM graph: FG -> HALB inputs; HALB -> sub-HALB / ROH / VERP.
    3. Collect all distinct SKU IDs touched.
    4. Output skus.xlsx sheet SKUS.

BOM structure: 2-layer flattened (FG→HALB, HALB→ROH/VERP).
HALB→HALB chains are resolved: intermediate HALBs appear as parents in layer 2.
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
BOM_CSV = SRC_DIR / "bom_by_product.csv"
SKU_CLASS_CSV = SRC_DIR / "SKU_Classification_20260527_sku分类明细.csv"

OUT_PATH = Path(__file__).resolve().parents[2] / "data" / "skus.xlsx"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_PALLET_SIZE_FG = 100
DEFAULT_PALLET_SIZE_WIP = 100
DEFAULT_PALLET_SIZE_RAW = 100
DEFAULT_BOM_SPEED_FG = 5.0
DEFAULT_BOM_SPEED_HALB = 10.0


def load_fg_skus() -> pd.DataFrame:
    df = pd.read_csv(SHARE_CSV)
    df = df.rename(columns={"物料": "sku_id", "product_name": "name"})
    df = df[["sku_id", "name"]].copy()
    df["sku_id"] = df["sku_id"].astype(str)
    print(f"[FG] Loaded {len(df)} FG SKUs", file=sys.stderr)
    return df


def load_bom() -> pd.DataFrame:
    df = pd.read_csv(BOM_CSV)
    df = df.rename(columns={
        "产品物料号": "prod_id",
        "产品描述": "prod_name",
        "产品类型": "prod_type",
        "产品单位": "prod_unit",
        "投入物料号": "mat_id",
        "投入物料描述": "mat_name",
        "投入物料类型": "mat_type",
        "投入物料单位": "mat_unit",
        "单位消耗量": "unit_consumption",
    })
    df["prod_id"] = df["prod_id"].astype(str)
    df["mat_id"] = df["mat_id"].astype(str)
    df["unit_consumption"] = pd.to_numeric(df["unit_consumption"], errors="coerce").fillna(0.0)
    print(f"[BOM] Loaded {len(df)} BOM rows", file=sys.stderr)
    return df


def load_sku_classification() -> dict[str, int]:
    """Return {sku_id: pack_size} from SKU_Classification."""
    df = pd.read_csv(SKU_CLASS_CSV)
    df = df.rename(columns={"物料": "sku_id", "count": "pack_size"})
    df["sku_id"] = df["sku_id"].astype(str)
    df["pack_size"] = pd.to_numeric(df["pack_size"], errors="coerce")
    df = df.dropna(subset=["pack_size"])
    df["pack_size"] = df["pack_size"].astype(int)
    result = dict(zip(df["sku_id"], df["pack_size"]))
    print(f"[CLASS] Loaded pack sizes for {len(result)} SKUs", file=sys.stderr)
    return result


def collect_all_skus(fg_ids: set[str], bom: pd.DataFrame) -> dict[str, dict]:
    """Walk the BOM tree and collect all SKU metadata.

    Returns dict sku_id -> {name, prod_type, prod_unit, mat_type, mat_unit, layer}
    """
    # Build lookup: prod_id -> list of material rows
    bom_by_prod: dict[str, list[dict]] = {}
    for _, row in bom.iterrows():
        pid = row["prod_id"]
        bom_by_prod.setdefault(pid, []).append({
            "prod_name": row["prod_name"],
            "prod_type": row["prod_type"],
            "prod_unit": row["prod_unit"],
            "mat_id": row["mat_id"],
            "mat_name": row["mat_name"],
            "mat_type": row["mat_type"],
            "mat_unit": row["mat_unit"],
            "unit_consumption": row["unit_consumption"],
        })

    skus: dict[str, dict] = {}
    visited_halb: set[str] = set()

    def register(sku_id: str, name: str, unit: str, mat_type: str | None):
        if sku_id in skus:
            return
        skus[sku_id] = {
            "name": name or sku_id,
            "unit": unit or "",
            "mat_type": mat_type or "",
        }

    def walk_halb(halb_id: str) -> None:
        if halb_id in visited_halb:
            return
        visited_halb.add(halb_id)
        rows = bom_by_prod.get(halb_id, [])
        if not rows:
            print(f"  [WARN] HALB {halb_id} has no BOM rows (orphan)", file=sys.stderr)
            register(halb_id, halb_id, "", "HALB")
            return
        prod_name = rows[0]["prod_name"]
        prod_unit = rows[0]["prod_unit"]
        register(halb_id, prod_name, prod_unit, "HALB")
        for r in rows:
            mid = r["mat_id"]
            mtype = r["mat_type"]
            mname = r["mat_name"]
            munit = r["mat_unit"]
            if mtype in ("ROH", "VERP", "ROHA"):
                register(mid, mname, munit, mtype)
            elif mtype == "HALB":
                walk_halb(mid)
            else:
                # ERXB, UNKNOWN, FERT-as-input — treat as raw
                register(mid, mname, munit, mtype)

    for fg in fg_ids:
        rows = bom_by_prod.get(fg, [])
        if not rows:
            print(f"  [WARN] FG {fg} not found in BOM (registering without BOM)", file=sys.stderr)
            register(fg, fg, "CS", "FERT")
            continue
        prod_name = rows[0]["prod_name"]
        prod_unit = rows[0]["prod_unit"]
        register(fg, prod_name, prod_unit, "FERT")
        for r in rows:
            mid = r["mat_id"]
            mtype = r["mat_type"]
            mname = r["mat_name"]
            munit = r["mat_unit"]
            if mtype in ("ROH", "VERP", "ROHA"):
                register(mid, mname, munit, mtype)
            elif mtype == "HALB":
                walk_halb(mid)
            else:
                register(mid, mname, munit, mtype)

    return skus


def main() -> None:
    fg_df = load_fg_skus()
    fg_ids = set(fg_df["sku_id"])
    bom = load_bom()
    pack_sizes = load_sku_classification()

    all_skus = collect_all_skus(fg_ids, bom)
    print(f"[COLLECT] Total SKUs: {len(all_skus)}", file=sys.stderr)

    # Count by type
    by_type: dict[str, int] = {}
    for info in all_skus.values():
        t = info["mat_type"] or "UNKNOWN"
        by_type[t] = by_type.get(t, 0) + 1
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"[COLLECT]   {t}: {n}", file=sys.stderr)

    # Build output rows
    def default_palette(mat_type: str) -> int:
        if mat_type == "FERT":
            return DEFAULT_PALLET_SIZE_FG
        return DEFAULT_PALLET_SIZE_WIP if mat_type == "HALB" else DEFAULT_PALLET_SIZE_RAW

    def default_speed(mat_type: str) -> float:
        if mat_type == "FERT":
            return DEFAULT_BOM_SPEED_FG
        if mat_type == "HALB":
            return DEFAULT_BOM_SPEED_HALB
        return 0.0

    rows: list[dict] = []
    for sku_id in sorted(all_skus.keys()):
        info = all_skus[sku_id]
        mt = info["mat_type"]
        ps = pack_sizes.get(sku_id, default_palette(mt))
        speed = default_speed(mt)
        rows.append({
            "sku_id": sku_id,
            "name": info["name"],
            "bom_speed": speed,
            "pallet_size": ps,
            "unit": info["unit"],
        })

    out_df = pd.DataFrame(rows, columns=["sku_id", "name", "bom_speed", "pallet_size", "unit"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        out_df.to_excel(writer, sheet_name="SKUS", index=False)

    print(f"\n[SKUS] Wrote {OUT_PATH}", file=sys.stderr)
    print(f"[SKUS]   {len(out_df)} SKUs", file=sys.stderr)
    fg_count = sum(1 for r in rows if r["sku_id"] in fg_ids)
    print(f"[SKUS]   FG: {fg_count}, Total: {len(rows)}", file=sys.stderr)


if __name__ == "__main__":
    main()
