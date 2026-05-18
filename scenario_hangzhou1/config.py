"""Simulation configuration for hangzhou1 — 4-SKU multi-package scenario.

SKUs (21)
---------
raw, 16 × WIP packages, 4 × FG

Flow
----
  source                       (供应商)
    -> raw_wh                  (原料库)
      -> line_side             (线边仓)
        -> factory_power       ---produces powerpackage_{a,b,c,d}--> pkg_wh
        -> factory_sauce       ---produces saucepackage_{a,b,c,d}--> pkg_wh
        -> factory_veg         ---produces vegpackage_{a,b,c,d}--> pkg_wh
        -> factory_outer       ---produces outerpackage_{a,b,c,d}--> pkg_wh
      -> pkg_wh                (料包库)
        -> assembly_a          ---produces sku_a--> fg_wh
        -> assembly_b          ---produces sku_b--> fg_wh
        -> assembly_c          ---produces sku_c--> fg_wh
        -> assembly_d          ---produces sku_d--> fg_wh
      -> fg_wh                 (成品库) -> sink (发货)

BOM
---
  Each package:   1 raw        -> 1 xxxpackage      (speed=20/min)
  Each FG:        1 of each package type -> 1 sku_x (speed=10/min)
"""

from src.edge import TransferMode

SKUS = {
    "raw": "原料",
    "powerpackage_a": "粉包A", "saucepackage_a": "酱包A",
    "vegpackage_a": "菜包A", "outerpackage_a": "外包A",
    "powerpackage_b": "粉包B", "saucepackage_b": "酱包B",
    "vegpackage_b": "菜包B", "outerpackage_b": "外包B",
    "powerpackage_c": "粉包C", "saucepackage_c": "酱包C",
    "vegpackage_c": "菜包C", "outerpackage_c": "外包C",
    "powerpackage_d": "粉包D", "saucepackage_d": "酱包D",
    "vegpackage_d": "菜包D", "outerpackage_d": "外包D",
    "sku_a": "成品A",
    "sku_b": "成品B",
    "sku_c": "成品C",
    "sku_d": "成品D",
}

PALLET_SIZE = {
    "raw": 100,
    "powerpackage_a": 100, "saucepackage_a": 100,
    "vegpackage_a": 100, "outerpackage_a": 100,
    "powerpackage_b": 100, "saucepackage_b": 100,
    "vegpackage_b": 100, "outerpackage_b": 100,
    "powerpackage_c": 100, "saucepackage_c": 100,
    "vegpackage_c": 100, "outerpackage_c": 100,
    "powerpackage_d": 100, "saucepackage_d": 100,
    "vegpackage_d": 100, "outerpackage_d": 100,
    "sku_a": 50,
    "sku_b": 50,
    "sku_c": 50,
    "sku_d": 50,
}

# ---------------------------------------------------------------------------
# Shared BOM fragments to reduce repetition
# ---------------------------------------------------------------------------

# Each package factory produces 4 variants (a/b/c/d), each taking 1 raw.
_PACKAGE_BOM = {
    f"{pkg_type}_{suffix}": {
        "inputs": {"raw": 1},
        "speed": 20.0,
        "lead_time": 0,
    }
    for pkg_type in ("powerpackage", "saucepackage", "vegpackage", "outerpackage")
    for suffix in ("a", "b", "c", "d")
}

# Each assembly line takes 4 specific packages to make 1 FG.
def _assembly_bom(fg_sku: str, suffix: str) -> dict:
    return {
        fg_sku: {
            "inputs": {
                f"powerpackage_{suffix}": 1,
                f"saucepackage_{suffix}": 1,
                f"vegpackage_{suffix}": 1,
                f"outerpackage_{suffix}": 1,
            },
            "speed": 10.0,
            "lead_time": 0,
        },
    }

# Conversion factor per package type
_PKG_CF = {f"{pkg_type}_{suffix}": 100
           for pkg_type in ("powerpackage", "saucepackage", "vegpackage", "outerpackage")
           for suffix in ("a", "b", "c", "d")}

# ---------------------------------------------------------------------------
# Node definitions
# ---------------------------------------------------------------------------

NODES = {
    # -- supply --
    "source": {
        "type": "source",
        "dispatch_interval": 1,
        "dispatch_max_pallets": 999,
        "display_name": "供应商",
    },
    "raw_wh": {
        "type": "warehouse",
        "max_pallets": 2000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "原料库",
    },
    "line_side": {
        "type": "warehouse",
        "max_pallets": 2000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "线边仓",
    },
    # -- 4 package factories (power / sauce / veg / outer) --
    "factory_power": {
        "type": "production",
        "upstream": "line_side",
        "downstream": "pkg_wh",
        "global_time_step": 10.0,
        "bom": {k: v for k, v in _PACKAGE_BOM.items() if k.startswith("powerpackage_")},
        "conversion_factors": {k: v for k, v in _PKG_CF.items() if k.startswith("powerpackage_")},
        "display_name": "粉包车间",
    },
    "factory_sauce": {
        "type": "production",
        "upstream": "line_side",
        "downstream": "pkg_wh",
        "global_time_step": 10.0,
        "bom": {k: v for k, v in _PACKAGE_BOM.items() if k.startswith("saucepackage_")},
        "conversion_factors": {k: v for k, v in _PKG_CF.items() if k.startswith("saucepackage_")},
        "display_name": "酱包车间",
    },
    "factory_veg": {
        "type": "production",
        "upstream": "line_side",
        "downstream": "pkg_wh",
        "global_time_step": 10.0,
        "bom": {k: v for k, v in _PACKAGE_BOM.items() if k.startswith("vegpackage_")},
        "conversion_factors": {k: v for k, v in _PKG_CF.items() if k.startswith("vegpackage_")},
        "display_name": "菜包车间",
    },
    "factory_outer": {
        "type": "production",
        "upstream": "line_side",
        "downstream": "pkg_wh",
        "global_time_step": 10.0,
        "bom": {k: v for k, v in _PACKAGE_BOM.items() if k.startswith("outerpackage_")},
        "conversion_factors": {k: v for k, v in _PKG_CF.items() if k.startswith("outerpackage_")},
        "display_name": "外包车间",
    },
    # -- central package warehouse --
    "pkg_wh": {
        "type": "warehouse",
        "max_pallets": 5000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 999,
        "display_name": "料包库",
    },
    # -- 4 assembly lines --
    "assembly_a": {
        "type": "production",
        "upstream": "pkg_wh",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": _assembly_bom("sku_a", "a"),
        "conversion_factors": {"sku_a": 50},
        "display_name": "装配线A",
    },
    "assembly_b": {
        "type": "production",
        "upstream": "pkg_wh",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": _assembly_bom("sku_b", "b"),
        "conversion_factors": {"sku_b": 50},
        "display_name": "装配线B",
    },
    "assembly_c": {
        "type": "production",
        "upstream": "pkg_wh",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": _assembly_bom("sku_c", "c"),
        "conversion_factors": {"sku_c": 50},
        "display_name": "装配线C",
    },
    "assembly_d": {
        "type": "production",
        "upstream": "pkg_wh",
        "downstream": "fg_wh",
        "global_time_step": 10.0,
        "bom": _assembly_bom("sku_d", "d"),
        "conversion_factors": {"sku_d": 50},
        "display_name": "装配线D",
    },
    # -- finished goods --
    "fg_wh": {
        "type": "warehouse",
        "max_pallets": 2000,
        "dispatch_interval": 2,
        "dispatch_max_pallets": 20,
        "display_name": "成品库",
    },
    "sink": {
        "type": "sink",
        "display_name": "发货",
    },
}

# ---------------------------------------------------------------------------
# Transport edges  (warehouse → warehouse)
# ---------------------------------------------------------------------------

EDGES = [
    {"from_node": "source", "to_node": "raw_wh",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
    {"from_node": "raw_wh", "to_node": "line_side",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
    {"from_node": "fg_wh", "to_node": "sink",
     "transfer_mode": TransferMode.BATCH, "transfer_time": 1, "batch_size": 50},
]

BASIC_TIME_UNIT = "MINUTE"
SIM_DURATION = 15000   # ~10.4 days
DAY = 60 * 24
SHIFT_STARTS = [480, 1200]     # 08:00, 20:00
SHIFT_DURATION = 690           # 11.5 hours per shift
