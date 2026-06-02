"""SKU definitions and pallet sizes for the Hangzhou scenario.

Loads from two Excel files when available:

    data/skus.xlsx   —  SKU metadata  (sku_id, name, pallet_size, bom_speed, unit)
    data/bom.xlsx    —  BOM relations  (sku_id, material_id, amount)

Falls back to hardcoded data when the files are absent.
"""

import sys
from pathlib import Path

import pandas as pd

from src.model.sku import SKU

N = 10  # Number of FG SKUs


def _load_from_excel() -> tuple[dict[str, SKU], dict[str, int]]:
    """Load SKUS / PALLET_SIZE from data/skus.xlsx + data/bom.xlsx.

    Prints a digest to stderr describing the loaded data.
    """
    root = Path(__file__).resolve().parents[2]
    sku_path = root / "data" / "skus.xlsx"
    bom_path = root / "data" / "bom.xlsx"

    meta = pd.read_excel(sku_path, sheet_name="SKUS")
    bom = pd.read_excel(bom_path, sheet_name="BOM")

    # --- Build SKU objects from metadata ---
    skus: dict[str, SKU] = {}
    pallet_size: dict[str, int] = {}

    for _, row in meta.iterrows():
        sku_id = str(row["sku_id"])
        skus[sku_id] = SKU(
            id=sku_id,
            name=str(row.get("name", sku_id) or sku_id),
            bom_speed=float(row.get("bom_speed", 0) or 0),
            pallet_size=int(row.get("pallet_size", 100) or 100),
            unit=str(row.get("unit", "") or ""),
        )
        pallet_size[sku_id] = skus[sku_id].pallet_size

    # --- Attach BOM data ---
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

    # --- Digest ---
    n_sku = len(skus)
    n_with_bom = sum(1 for s in skus.values() if s.bom)
    n_no_bom = n_sku - n_with_bom

    print(f"[SKU] Loaded {n_sku} SKUs from Excel", file=sys.stderr)
    print(f"[SKU]   {n_with_bom} have BOM (producible)", file=sys.stderr)
    print(f"[SKU]   {n_no_bom} have no BOM (raw materials)", file=sys.stderr)
    if bad_refs:
        print(f"[SKU]   WARNING: {len(bad_refs)} BOM rows reference unknown SKUs:", file=sys.stderr)
        for sku_id, mat_id in bad_refs:
            print(f"[SKU]     {sku_id} → {mat_id} (NOT in skus.xlsx)", file=sys.stderr)
    else:
        print(f"[SKU]   All BOM material references are valid", file=sys.stderr)

    return skus, pallet_size


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

root = Path(__file__).resolve().parents[2]
sku_path = root / "data" / "skus.xlsx"

if sku_path.exists():
    SKUS, PALLET_SIZE = _load_from_excel()
else:
    # Hardcoded fallback
    SKUS: dict[str, SKU] = {}
    PALLET_SIZE: dict[str, int] = {}

    # -- Raw materials for sauce production --
    for i in range(1, N + 1):
        sku_id = f"smallpack_s_{i}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"酱包小包{i}", pallet_size=100)
        PALLET_SIZE[sku_id] = 100
    for l in range(1, 5):
        sku_id = f"meat_{l}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"肉{l}", pallet_size=100)
        PALLET_SIZE[sku_id] = 100
    for j in range(1, 5):
        sku_id = f"oil_{j}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"油{j}", pallet_size=100)
        PALLET_SIZE[sku_id] = 100
    for k in range(1, 5):
        sku_id = f"vegetable_{k}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"蔬菜{k}", pallet_size=100)
        PALLET_SIZE[sku_id] = 100

    # -- Raw materials for powder production --
    for i in range(1, N + 1):
        sku_id = f"smallpack_p_{i}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"粉包小包{i}", pallet_size=100)
        PALLET_SIZE[sku_id] = 100
    for k in range(1, 6):
        sku_id = f"original_powder_{k}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"原粉{k}", pallet_size=100)
        PALLET_SIZE[sku_id] = 100

    # -- Raw materials for veg production --
    for i in range(1, N + 1):
        sku_id = f"smallpack_v_{i}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"菜包小包{i}", pallet_size=100)
        PALLET_SIZE[sku_id] = 100
    for k in range(1, 5):
        sku_id = f"dry_veg_{k}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"干菜{k}", pallet_size=100)
        PALLET_SIZE[sku_id] = 100

    # -- Packaging materials --
    for pkg_id, pkg_name in [("bow", "碗"), ("cap", "盖"), ("pack", "外包装")]:
        SKUS[pkg_id] = SKU(id=pkg_id, name=pkg_name, pallet_size=100)
        PALLET_SIZE[pkg_id] = 100

    # -- WIP SKUs (sauce, powder, veg) --
    _sauce_meat = [1, 2, 3, 4, 1, 2, 3, 4, 1, 2]
    _sauce_oil = [1, 2, 3, 4, 2, 3, 4, 1, 3, 4]
    _sauce_veg = [1, 2, 3, 4, 3, 4, 1, 2, 3, 1]

    for i in range(1, N + 1):
        idx = i - 1
        sku_id = f"sauce_{i}"
        SKUS[sku_id] = SKU(
            id=sku_id,
            name=f"酱包{i}",
            bom={
                f"smallpack_s_{i}": 1,
                f"meat_{_sauce_meat[idx]}": 2,
                f"oil_{_sauce_oil[idx]}": 2,
                f"vegetable_{_sauce_veg[idx]}": 2,
            },
            bom_speed=10,
            pallet_size=100,
        )
        PALLET_SIZE[sku_id] = 100

    _powder_picks = [
        (1, 2, 3), (2, 3, 4), (3, 4, 5), (4, 5, 1), (5, 1, 2),
        (1, 3, 5), (2, 4, 1), (3, 5, 2), (4, 1, 3), (5, 2, 4),
    ]
    for i in range(1, N + 1):
        a, b, c = _powder_picks[i - 1]
        sku_id = f"powder_{i}"
        SKUS[sku_id] = SKU(
            id=sku_id,
            name=f"粉包{i}",
            bom={
                f"smallpack_p_{i}": 1,
                f"original_powder_{a}": 1,
                f"original_powder_{b}": 1,
                f"original_powder_{c}": 1,
            },
            bom_speed=10,
            pallet_size=100,
        )
        PALLET_SIZE[sku_id] = 100

    _veg_picks = [
        (1, 2), (2, 3), (3, 4), (4, 1),
        (1, 3), (2, 4), (1, 4), (2, 3),
        (3, 1), (4, 2),
    ]
    for i in range(1, N + 1):
        a, b = _veg_picks[i - 1]
        sku_id = f"veg_{i}"
        SKUS[sku_id] = SKU(
            id=sku_id,
            name=f"菜包{i}",
            bom={
                f"smallpack_v_{i}": 1,
                f"dry_veg_{a}": 1,
                f"dry_veg_{b}": 1,
            },
            bom_speed=100,
            pallet_size=100,
        )
        PALLET_SIZE[sku_id] = 100

    # -- FG SKUs --
    for i in range(1, N + 1):
        sku_id = f"SKU_{i}"
        inputs = {f"sauce_{i}": 1, f"powder_{i}": 1, f"veg_{i}": 1}
        if i % 2 == 0:
            inputs["bow"] = 1
            inputs["cap"] = 1
        else:
            inputs["pack"] = 1
        SKUS[sku_id] = SKU(
            id=sku_id,
            name=f"成品{i}",
            bom=inputs,
            bom_speed=5,
            pallet_size=50,
        )
        PALLET_SIZE[sku_id] = 50