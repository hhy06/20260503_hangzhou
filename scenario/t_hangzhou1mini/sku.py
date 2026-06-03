"""SKU definitions and pallet sizes for the Hangzhou scenario.

Loads from data/skus.xlsx + data/bom.xlsx via :mod:`src._xlsx_loaders`.

Falls back to hardcoded data when the xlsx files are absent.
"""

from pathlib import Path

from src.model.sku import SKU

N = 10  # Number of FG SKUs

root = Path(__file__).resolve().parents[2] / "data"
sku_path = root / "skus.xlsx"

if sku_path.exists():
    from src._xlsx_loaders import load_skus_and_bom
    SKUS = load_skus_and_bom(root)
else:
    SKUS: dict[str, SKU] = {}

    # -- Raw materials for sauce production --
    for i in range(1, N + 1):
        sku_id = f"smallpack_s_{i}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"酱包小包装{i}", pallet_size=100)
    for l in range(1, 5):
        sku_id = f"meat_{l}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"肉{l}", pallet_size=100)
    for j in range(1, 5):
        sku_id = f"oil_{j}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"油{j}", pallet_size=100)
    for k in range(1, 5):
        sku_id = f"vegetable_{k}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"蔬菜{k}", pallet_size=100)

    # -- Raw materials for powder production --
    for i in range(1, N + 1):
        sku_id = f"smallpack_p_{i}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"粉包小包装{i}", pallet_size=100)
    for k in range(1, 6):
        sku_id = f"original_powder_{k}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"原粉{k}", pallet_size=100)

    # -- Raw materials for veg production --
    for i in range(1, N + 1):
        sku_id = f"smallpack_v_{i}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"菜包小包装{i}", pallet_size=100)
    for k in range(1, 5):
        sku_id = f"dry_veg_{k}"
        SKUS[sku_id] = SKU(id=sku_id, name=f"干菜{k}", pallet_size=100)

    # -- Packaging materials --
    for pkg_id, pkg_name in [("bow", "碗"), ("cap", "盖"), ("pack", "外包装")]:
        SKUS[pkg_id] = SKU(id=pkg_id, name=pkg_name, pallet_size=100)

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

    # -- FG SKUs --
    for i in range(1, N + 1):
        sku_id = f"SKU_{i}"
        inputs = {f"sauce_{i}": 20, f"powder_{i}": 20, f"veg_{i}": 20}
        if i % 2 == 0:
            inputs["bow"] = 20
            inputs["cap"] = 20
        else:
            inputs["pack"] = 20
        SKUS[sku_id] = SKU(
            id=sku_id,
            name=f"成品面{i}",
            bom=inputs,
            bom_speed=5,
            pallet_size=50,
        )