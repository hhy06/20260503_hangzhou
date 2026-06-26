"""SKU definitions for srw_hangzhou1_90d.

SKU master data is loaded from skus.xlsx + bom.xlsx (local to this scenario).
The xlsx files are mandatory.
"""

from pathlib import Path

from src.model.sku import SKU

N = 260

root = Path(__file__).resolve().parents[0]
sku_path = root / "skus.xlsx"

if not sku_path.exists():
    raise FileNotFoundError(
        f"srw_hangzhou1_90d requires {sku_path}. Run _generate_skus.py first."
    )

from src._xlsx_loaders import load_skus_and_bom
SKUS: dict[str, SKU] = load_skus_and_bom(root)
