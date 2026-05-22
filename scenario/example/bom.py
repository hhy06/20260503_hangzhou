"""Bill-of-materials for the simple linear example.

Both FG SKUs require one unit of raw_a and one unit of raw_b.
"""
from scenario.example.sku import N

_BOM: dict[str, dict] = {}

for sku in ("fg_x", "fg_y"):
    _BOM[sku] = {
        "inputs": {"raw_a": 1, "raw_b": 1},
        "speed": 0.05,
        "lead_time": 0,
    }

# Re-export as the standard name consumers expect.
FG_BOM = _BOM
