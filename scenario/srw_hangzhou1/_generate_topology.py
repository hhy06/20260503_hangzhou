"""Generate plant_topology.py for scenario rw_hangzhou1.

Reads:
    ~/transf/temp/masterkong_large_康师傅/sku_line_feasibility.csv
    ~/transf/temp/masterkong_large_康师傅/bom_by_product.csv

Outputs:
    scenario/rw_hangzhou1/plant_topology.py  (Python with NODES + EDGES dicts)

Topology design:
    Pool nodes:  source, raw_material_storage, soup_storage,
                 sauce_wip_storage, powder_wip_storage, veg_wip_storage,
                 fg_storage, sink

    Per line (×88):  lineside_{id} -> workstation_{id} -> output_{id}

    Line category -> upstream/downstream pools:
        J / ZJ (熟酱)     : upstream=raw_material_storage, downstream=soup_storage
        0xx (酱包/醋包/油包): upstream=raw_material_storage+soup_storage, downstream=sauce_wip_storage
        C / DC / XC (菜包) : upstream=raw_material_storage, downstream=veg_wip_storage
        F / FB / H / DF / ZL (粉包): upstream=raw_material_storage, downstream=powder_wip_storage
        X (成品组装)         : upstream=multiple WIP pools, downstream=fg_storage
        RP (杂项)          : upstream=raw_material_storage, downstream=soup_storage
"""

from __future__ import annotations

from pathlib import Path
import sys
from collections import defaultdict
from textwrap import indent

import pandas as pd

SRC_DIR = Path.home() / "transf" / "temp" / "masterkong_large_康师傅"
FEAS_CSV = SRC_DIR / "sku_line_feasibility.csv"
BOM_CSV = SRC_DIR / "bom_by_product.csv"

OUT_PATH = Path(__file__).resolve().parents[0] / "plant_topology.py"
SKUS_XLSX = Path(__file__).resolve().parents[2] / "data" / "skus.xlsx"


def classify_line(line_id: str, feasible_skus: list[str]) -> str:
    """Return category based on line ID and what it produces."""
    if line_id.startswith("J"):
        return "J_soup"
    if line_id == "ZJ1":
        return "J_soup"
    if line_id in ("XC1", "XC2"):
        return "C_veg"
    if line_id.startswith("DC"):
        return "C_veg"
    if line_id.startswith("C"):
        return "C_veg"
    if line_id in ("DF1", "ZL1"):
        return "F_powder"
    if line_id.startswith("H"):
        return "F_powder"
    if line_id.startswith("F"):
        return "F_powder"
    if line_id.startswith("X"):
        return "X_fert"
    if line_id == "RP1":
        return "RP_misc"
    # 0xx numeric lines: 001-008, 012, 09A-11B
    return "0_sauce"


CATEGORY_DISPLAY = {
    "J_soup": "熟酱",
    "0_sauce": "酱包/油包/醋包",
    "C_veg": "菜包",
    "F_powder": "粉包/粉菜包",
    "X_fert": "成品组装",
    "RP_misc": "杂项",
}

CATEGORY_DOWNSTREAM = {
    "J_soup": "soup_storage",
    "0_sauce": "sauce_wip_storage",
    "C_veg": "veg_wip_storage",
    "F_powder": "powder_wip_storage",
    "X_fert": "fg_storage",
    "RP_misc": "soup_storage",
}

CATEGORY_SPEED = {
    "J_soup": 10.0,
    "0_sauce": 10.0,
    "C_veg": 10.0,
    "F_powder": 10.0,
    "X_fert": 5.0,
    "RP_misc": 10.0,
}


def load_data():
    feas = pd.read_csv(FEAS_CSV)
    feas.rename(columns={
        "产线": "line", "产线类型": "ltype",
        "SKU物料号": "sku", "SKU描述": "sku_desc",
        "出现班次数": "shifts", "总产量": "total_output",
    }, inplace=True)
    feas["line"] = feas["line"].astype(str)
    feas["sku"] = feas["sku"].astype(str)

    bom = pd.read_csv(BOM_CSV)
    bom.rename(columns={
        "产品物料号": "prod_id", "投入物料号": "mat_id",
        "投入物料类型": "mat_type", "单位消耗量": "amount",
    }, inplace=True)
    bom["prod_id"] = bom["prod_id"].astype(str)
    bom["mat_id"] = bom["mat_id"].astype(str)
    bom["amount"] = pd.to_numeric(bom["amount"], errors="coerce").fillna(0.0)
    bom = bom[bom["amount"] > 0]

    bom_lookup: dict[str, dict[str, float]] = {}
    for _, row in bom.iterrows():
        pid, mid, amt = row["prod_id"], row["mat_id"], row["amount"]
        if pid not in bom_lookup:
            bom_lookup[pid] = {}
        bom_lookup[pid][mid] = bom_lookup[pid].get(mid, 0) + amt

    return feas, bom_lookup


def group_lines(feas: pd.DataFrame) -> dict[str, dict]:
    """Return {line_id: {fezible_skus, category, ltype, ...}}."""
    result = {}
    for line, grp in feas.groupby("line"):
        skus = grp["sku"].tolist()
        ltypes = grp["ltype"].unique()
        ltype = "FERT" if "FERT" in ltypes else "HALB"
        cat = classify_line(line, skus)
        result[line] = {
            "skus": skus,
            "category": cat,
            "ltype": ltype,
            "display_cat": CATEGORY_DISPLAY[cat],
        }
    return result


def build_workspace_bom(line_skus: list[str], bom_lookup: dict[str, dict[str, float]],
                        sku_set: set[str]) -> dict[str, dict]:
    """Build BOM dict for a workstation: {sku: {inputs: {mat: amt}, speed: 0, lead_time: 0}}.

    Only includes outputs and inputs that exist in sku_set.
    """
    result = {}
    for sku in sorted(set(line_skus)):
        if sku not in sku_set:
            continue
        inputs = bom_lookup.get(sku, {})
        if not inputs:
            continue
        valid_inputs = {m: a for m, a in inputs.items() if m in sku_set}
        if not valid_inputs:
            continue
        result[sku] = {
            "inputs": valid_inputs,
            "speed": 0,
            "lead_time": 0,
        }
    return result


def generate(lines: dict[str, dict], bom_lookup: dict[str, dict[str, float]],
             sku_set: set[str]) -> str:
    out = []
    out.append('"""Plant topology for rw_hangzhou1 (auto-generated).')
    out.append("")
    out.append(f"88 production lines, {sum(len(v['skus']) for v in lines.values())} line-SKU pairs.")
    out.append("Generated by _generate_topology.py from sku_line_feasibility.csv + bom_by_product.csv.")
    out.append('"""')
    out.append("")
    out.append("from src.infrastructure.edge import TransferMode")
    out.append("")

    # NODES
    out.append("NODES: dict[str, dict] = {}")
    out.append("")

    # Pool nodes
    out.append('# -- Pool nodes --')
    out.append('NODES["source"] = {"type": "source", "display_name": "供应商"}')
    out.append("")
    out.append('NODES["raw_material_storage"] = {')
    out.append('    "type": "warehouse", "max_pallets": 50000,')
    out.append('    "dispatch_interval": 2, "dispatch_max_pallets": 50,')
    out.append('    "display_name": "原料库",')
    out.append('}')
    out.append("")
    out.append('NODES["soup_storage"] = {')
    out.append('    "type": "warehouse", "max_pallets": 5000,')
    out.append('    "display_name": "熟酱库",')
    out.append('}')
    out.append("")
    out.append('NODES["sauce_wip_storage"] = {')
    out.append('    "type": "warehouse", "max_pallets": 10000,')
    out.append('    "display_name": "酱包/油包/醋包半成品库",')
    out.append('}')
    out.append("")
    out.append('NODES["powder_wip_storage"] = {')
    out.append('    "type": "warehouse", "max_pallets": 10000,')
    out.append('    "display_name": "粉包半成品库",')
    out.append('}')
    out.append("")
    out.append('NODES["veg_wip_storage"] = {')
    out.append('    "type": "warehouse", "max_pallets": 10000,')
    out.append('    "display_name": "菜包半成品库",')
    out.append('}')
    out.append("")
    out.append('NODES["fg_storage"] = {')
    out.append('    "type": "warehouse", "max_pallets": 50000,')
    out.append('    "display_name": "成品库",')
    out.append('}')
    out.append("")
    out.append('NODES["sink"] = {"type": "sink", "display_name": "发货"}')
    out.append("")

    # Per-line nodes (sorted by category then line ID)
    cat_display_names = {}
    for cat in ["J_soup", "0_sauce", "C_veg", "F_powder", "X_fert", "RP_misc"]:
        cat_lines = sorted((lid, info) for lid, info in lines.items() if info["category"] == cat)
        if not cat_lines:
            continue
        cat_name = CATEGORY_DISPLAY[cat]
        out.append(f"# -- {cat_name} lines ({len(cat_lines)}) --")
        for lid, info in cat_lines:
            speed = CATEGORY_SPEED[cat]
            display_name = f"{cat_name}_{lid}"
            bom = build_workspace_bom(info["skus"], bom_lookup, sku_set)
            n_skus = len(bom)

            out.append(f'NODES["lineside_{lid}"] = {{')
            out.append(f'    "type": "warehouse", "max_pallets": 500,')
            out.append(f'    "display_name": "{display_name}_线边仓",')
            out.append(f'}}')

            out.append(f'NODES["workstation_{lid}"] = {{')
            out.append(f'    "type": "production",')
            out.append(f'    "upstream": "lineside_{lid}",')
            out.append(f'    "downstream": "output_{lid}",')
            bom_str = repr(bom)
            out.append(f'    "bom": {bom_str},')
            out.append(f'    "global_time_step": 60.0,')
            out.append(f'    "display_name": "{display_name}_车间",')
            out.append(f'    "shift_duration": 690,')
            out.append(f'    "decision_offset": 60,')
            out.append(f'    "production_start_times": [480, 1200],')
            out.append(f'}}')

            out.append(f'NODES["output_{lid}"] = {{')
            out.append(f'    "type": "warehouse", "max_pallets": 500,')
            out.append(f'    "display_name": "{display_name}_产出缓存",')
            out.append(f'}}')
            out.append("")

    # EDGES
    out.append("# =========================================================================")
    out.append("# Edges")
    out.append("# =========================================================================")
    out.append("")
    out.append("EDGES: list[dict] = []")
    out.append("")

    # source -> raw_material_storage
    out.append('# Source -> raw_material_storage')
    out.append('EDGES.append({')
    out.append('    "from_node": "source", "to_node": "raw_material_storage",')
    out.append('    "transfer_mode": TransferMode.BATCH,')
    out.append('    "batch_transport_time": 0.0, "batch_pallets": 1000,')
    out.append('})')
    out.append("")

    for cat in ["J_soup", "0_sauce", "C_veg", "F_powder", "X_fert", "RP_misc"]:
        cat_lines = sorted((lid, info) for lid, info in lines.items() if info["category"] == cat)
        if not cat_lines:
            continue
        cat_name = CATEGORY_DISPLAY[cat]
        out.append(f"# -- {cat_name} --")

        for lid, info in cat_lines:
            ds_pool = CATEGORY_DOWNSTREAM[cat]

            # raw_material_storage -> lineside
            out.append(f'EDGES.append({{')
            out.append(f'    "from_node": "raw_material_storage", "to_node": "lineside_{lid}",')
            out.append(f'    "transfer_mode": TransferMode.BATCH,')
            out.append(f'    "batch_transport_time": 1.0, "batch_pallets": 1000,')
            out.append(f'}})')

            # Extra upstream for 0_sauce: soup_storage -> lineside
            if cat == "0_sauce":
                out.append(f'EDGES.append({{')
                out.append(f'    "from_node": "soup_storage", "to_node": "lineside_{lid}",')
                out.append(f'    "transfer_mode": TransferMode.BATCH,')
                out.append(f'    "batch_transport_time": 1.0, "batch_pallets": 1000,')
                out.append(f'}})')

            # Extra upstream for X_fert: all WIP pools -> lineside
            if cat == "X_fert":
                for pool in ["sauce_wip_storage", "powder_wip_storage", "veg_wip_storage"]:
                    out.append(f'EDGES.append({{')
                    out.append(f'    "from_node": "{pool}", "to_node": "lineside_{lid}",')
                    out.append(f'    "transfer_mode": TransferMode.BATCH,')
                    out.append(f'    "batch_transport_time": 1.0, "batch_pallets": 1000,')
                    out.append(f'}})')
                # packaging from raw_material_storage is already covered above

            # output_{lid} -> downstream pool
            out.append(f'EDGES.append({{')
            out.append(f'    "from_node": "output_{lid}", "to_node": "{ds_pool}",')
            out.append(f'    "transfer_mode": TransferMode.BATCH,')
            out.append(f'    "batch_transport_time": 1.0, "batch_pallets": 1000,')
            out.append(f'}})')
            out.append("")

    # fg_storage -> sink
    out.append("# -- fg_storage -> sink --")
    out.append('EDGES.append({')
    out.append('    "from_node": "fg_storage", "to_node": "sink",')
    out.append('    "transfer_mode": TransferMode.BATCH,')
    out.append('    "batch_transport_time": 5.0, "batch_pallets": 1000,')
    out.append('})')

    return "\n".join(out) + "\n"


def main():
    feas, bom_lookup = load_data()
    lines = group_lines(feas)

    sku_df = pd.read_excel(SKUS_XLSX)
    sku_set: set[str] = set(sku_df["sku_id"].astype(str))
    print(f"[TOPOLOGY] SKU universe: {len(sku_set)}", file=sys.stderr)

    n_total_skus = sum(len(v["skus"]) for v in lines.values())
    print(f"[TOPOLOGY] {len(lines)} lines, {n_total_skus} line-SKU pairs", file=sys.stderr)
    for cat in ["J_soup", "0_sauce", "C_veg", "F_powder", "X_fert", "RP_misc"]:
        n = sum(1 for v in lines.values() if v["category"] == cat)
        if n > 0:
            print(f"[TOPOLOGY]   {cat}: {n} lines", file=sys.stderr)

    code = generate(lines, bom_lookup, sku_set)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(code, encoding="utf-8")

    n_nodes = code.count('"type"')
    n_edges = code.count('EDGES.append')
    print(f"[TOPOLOGY] Wrote {OUT_PATH}", file=sys.stderr)
    print(f"[TOPOLOGY]   Nodes: {n_nodes}", file=sys.stderr)
    print(f"[TOPOLOGY]   Edges: {n_edges}", file=sys.stderr)


if __name__ == "__main__":
    main()
