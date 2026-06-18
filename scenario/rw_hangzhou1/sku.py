"""SKU definitions for rw_hangzhou1.

SKU master data is loaded from data/skus.xlsx + data/bom.xlsx.
The xlsx files are mandatory.
"""

from pathlib import Path

from src.model.sku import SKU

N = 260

root = Path(__file__).resolve().parents[2] / "data"
sku_path = root / "skus.xlsx"

if not sku_path.exists():
    raise FileNotFoundError(
        f"rw_hangzhou1 requires {sku_path}. Run _generate_skus.py first."
    )

from src._xlsx_loaders import load_skus_and_bom
SKUS: dict[str, SKU] = load_skus_and_bom(root)
