"""Generate plant_topology.py for scenario srw_hangzhou1_90d.

New simplified DAG structure (compared to rw_hangzhou1):
  - Sauce packets (酱包) are now produced directly from ROH+VERP (no 熟酱 intermediate)
  - J lines produce sauce packets (酱包) instead of 熟酱
  - Simplified pool structure: wip_storage (粉/酱), veg_wip_storage, prep_storage_1/2
  - Virtual edges (transport_time=0) for internal transfers

Reads:
    ~/transf/temp/masterkong_large_康师傅/sku_line_feasibility.csv
    ~/transf/temp/masterkong_large_康师傅/simple_bom_by_product.csv  (for BOM data)
    ~/transf/temp/masterkong_large_康师傅/bom_by_product.csv  (for 15N→sauce mapping)

Outputs:
    scenario/srw_hangzhou1_90d/plant_topology.py  (Python with NODES + EDGES dicts)

Topology design:
    Pool nodes:
      source (供应商)
      raw_material_storage (原物料库) - for J/F lines
      veg_raw_storage (菜包原料库) - for C lines
      wip_storage (粉包/酱包半成品库) - receives from J/F lines
      veg_wip_storage (菜包半成品库) - receives from C lines
      prep_storage_1 (1库) - feeds X00-X08
      prep_storage_2 (2库) - feeds X09-X15, X18
      fg_storage (成品库) - receives from X lines
      sink (发货)

    Per line (×72):  lineside_{id} -> workstation_{id} -> output_{id}

    Line category -> upstream/downstream pools:
        J (酱包)     : upstream=raw_material_storage, downstream=wip_storage
        C/DC/XC (菜包): upstream=veg_raw_storage, downstream=veg_wip_storage
        F/FB/H/DF/ZL (粉包): upstream=raw_material_storage, downstream=wip_storage
        X (成品组装)   : upstream=prep_storage_1/2, downstream=fg_storage

    Sauce packet -> J line mapping:
        Read original bom_by_product.csv to find which 15N each sauce packet (1502/1507/1509) uses
        Read sku_line_feasibility.csv to find which J lines can produce which 15N
        Transitive closure: sauce -> 15N -> J lines
        Multiple J lines can produce the same sauce packet (保留多线能力)
        Unmapped sauce packets (no 15N) are round-robin distributed to all J lines
"""

from __future__ import annotations

from pathlib import Path
import sys
from collections import defaultdict

import pandas as pd

SRC_DIR = Path.home() / "transf" / "temp" / "masterkong_large_康师傅"
FEAS_CSV = SRC_DIR / "sku_line_feasibility.csv"
SIMPLE_BOM_CSV = SRC_DIR / "simple_bom_by_product.csv"
OLD_BOM_CSV = SRC_DIR / "bom_by_product.csv"

OUT_PATH = Path(__file__).resolve().parents[0] / "plant_topology.py"
SKUS_XLSX = Path(__file__).resolve().parents[0] / "skus.xlsx"


def classify_line(line_id: str) -> str:
    """Return category based on line ID."""
    if line_id.startswith("J") or line_id == "ZJ1":
        return "J_sauce"
    if line_id.startswith("X") and not line_id.startswith("XC"):
        return "X_fert"
    if line_id.startswith("C") or line_id.startswith("DC") or line_id in ("XC1", "XC2"):
        return "C_veg"
    if line_id.startswith("F") or line_id.startswith("FB") or line_id.startswith("H") or line_id in ("DF1", "ZL1"):
        return "F_powder"
    return "unknown"


CATEGORY_DISPLAY = {
    "J_sauce": "酱包",
    "C_veg": "菜包",
    "F_powder": "粉包",
    "X_fert": "成品组装",
}

CATEGORY_DOWNSTREAM = {
    "J_sauce": "wip_storage",
    "C_veg": "veg_wip_storage",
    "F_powder": "wip_storage",
    "X_fert": "fg_storage",
}

CATEGORY_UPSTREAM = {
    "J_sauce": "raw_material_storage",
    "C_veg": "veg_raw_storage",
    "F_powder": "raw_material_storage",
}

CATEGORY_SPEED = {
    "J_sauce": 10.0,
    "C_veg": 10.0,
    "F_powder": 10.0,
    "X_fert": 5.0,
}


def load_feasibility() -> dict[str, list[str]]:
    """Load feasibility and return {line_id: [sku_ids]}."""
    feas = pd.read_csv(FEAS_CSV)
    feas.rename(columns={
        "产线": "line",
        "SKU物料号": "sku",
    }, inplace=True)
    feas["line"] = feas["line"].astype(str)
    feas["sku"] = feas["sku"].astype(str)

    result = defaultdict(list)
    for _, row in feas.iterrows():
        result[row["line"]].append(row["sku"])

    return dict(result)


def load_simple_bom() -> dict[str, dict[str, float]]:
    """Load simple BOM and return {prod_id: {mat_id: amount}}."""
    bom = pd.read_csv(SIMPLE_BOM_CSV, encoding='utf-8-sig')
    bom.rename(columns={
        "产品物料号": "prod_id",
        "投入物料号": "mat_id",
        "单位消耗量": "amount",
    }, inplace=True)
    bom["prod_id"] = bom["prod_id"].astype(str)
    bom["mat_id"] = bom["mat_id"].astype(str)
    bom["amount"] = pd.to_numeric(bom["amount"], errors="coerce").fillna(0.0)
    bom = bom[bom["amount"] > 0]

    lookup: dict[str, dict[str, float]] = {}
    for _, row in bom.iterrows():
        pid, mid, amt = row["prod_id"], row["mat_id"], row["amount"]
        if pid not in lookup:
            lookup[pid] = {}
        lookup[pid][mid] = lookup[pid].get(mid, 0) + amt

    return lookup


def build_sauce_to_j_mapping() -> dict[str, set[str]]:
    """Build mapping: sauce_packet_id -> set{J_line_ids}.

    Uses original bom_by_product.csv to find which 15N each sauce packet uses,
    then uses feasibility to find which J lines can produce those 15N.
    """
    old_bom = pd.read_csv(OLD_BOM_CSV, encoding='utf-8-sig')
    old_bom.rename(columns={
        "产品物料号": "prod_id",
        "投入物料号": "mat_id",
    }, inplace=True)
    old_bom["prod_id"] = old_bom["prod_id"].astype(str)
    old_bom["mat_id"] = old_bom["mat_id"].astype(str)

    feas = load_feasibility()

    shujiang_to_j = defaultdict(set)
    for line_id, skus in feas.items():
        if classify_line(line_id) == "J_sauce":
            for sku in skus:
                if sku.startswith("15N"):
                    shujiang_to_j[sku].add(line_id)

    sauce_rows = old_bom[
        old_bom["prod_id"].str.startswith(("1502", "1507", "1509")) &
        old_bom["mat_id"].str.startswith("15N")
    ]

    sauce_to_j = defaultdict(set)
    for _, row in sauce_rows.iterrows():
        sauce_id = row["prod_id"]
        shujiang_id = row["mat_id"]
        sauce_to_j[sauce_id].update(shujiang_to_j.get(shujiang_id, set()))

    simple_bom_products = load_simple_bom()
    all_sauce = {pid for pid in simple_bom_products if pid.startswith(("1502", "1507", "1509"))}
    unmapped = all_sauce - set(sauce_to_j.keys())

    if unmapped:
        j_lines = sorted(lid for lid in feas if classify_line(lid) == "J_sauce")
        for i, sauce_id in enumerate(sorted(unmapped)):
            j_line = j_lines[i % len(j_lines)]
            sauce_to_j[sauce_id].add(j_line)
            print(f"[WARN] Sauce {sauce_id} has no 15N link, assigned to {j_line}", file=sys.stderr)

    return dict(sauce_to_j)


def filter_line_skus(line_id: str, cat: str, feas_skus: list[str],
                     sauce_to_j: dict[str, set[str]],
                     simple_bom: dict[str, dict[str, float]]) -> list[str]:
    """Filter feasibility SKUs based on line category and BOM availability."""
    if cat == "J_sauce":
        # J line produces sauce packets (from mapping, not from feasibility which has 15N)
        sauce_for_line = {sid for sid, jls in sauce_to_j.items() if line_id in jls}
        return sorted(sauce_for_line & set(simple_bom.keys()))
    else:
        return [s for s in feas_skus if s in simple_bom]


def build_workspace_bom(line_skus: list[str], simple_bom: dict[str, dict[str, float]],
                        sku_set: set[str]) -> dict[str, dict]:
    """Build BOM dict for a workstation: {sku: {inputs: {mat: amt}, speed: 0, lead_time: 0}}.

    Only includes outputs and inputs that exist in sku_set.
    """
    result = {}
    for sku in sorted(set(line_skus)):
        if sku not in sku_set:
            continue
        inputs = simple_bom.get(sku, {})
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


def prep_storage_for_x(line_id: str) -> str:
    """Return which prep_storage feeds this X line."""
    if line_id in {"X00", "X01", "X02", "X03", "X04", "X05", "X06", "X07", "X08"}:
        return "prep_storage_1"
    else:
        return "prep_storage_2"


def generate(lines: dict[str, dict], simple_bom: dict[str, dict[str, float]],
             sauce_to_j: dict[str, set[str]], sku_set: set[str]) -> str:
    out = []
    out.append('"""Plant topology for srw_hangzhou1_90d (auto-generated).')
    out.append("")
    total_line_skus = sum(len(v['skus']) for v in lines.values())
    out.append(f"72 production lines, {total_line_skus} line-SKU pairs.")
    out.append("Simplified DAG: J(酱包)/C(菜包)/F(粉包)/X(成品), with prep_storage_1/2 intermediate.")
    out.append("Generated by _generate_topology.py from simple_bom_by_product.csv + bom_by_product.csv.")
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
    out.append('    "display_name": "原物料库",')
    out.append('}')
    out.append("")
    out.append('NODES["veg_raw_storage"] = {')
    out.append('    "type": "warehouse", "max_pallets": 10000,')
    out.append('    "display_name": "菜包原料库",')
    out.append('}')
    out.append("")
    out.append('NODES["wip_storage"] = {')
    out.append('    "type": "warehouse", "max_pallets": 20000,')
    out.append('    "display_name": "粉包/酱包半成品库",')
    out.append('}')
    out.append("")
    out.append('NODES["veg_wip_storage"] = {')
    out.append('    "type": "warehouse", "max_pallets": 10000,')
    out.append('    "display_name": "菜包半成品库",')
    out.append('}')
    out.append("")
    out.append('NODES["prep_storage_1"] = {')
    out.append('    "type": "warehouse", "max_pallets": 30000,')
    out.append('    "display_name": "1库",')
    out.append('}')
    out.append("")
    out.append('NODES["prep_storage_2"] = {')
    out.append('    "type": "warehouse", "max_pallets": 30000,')
    out.append('    "display_name": "2库",')
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
    for cat in ["J_sauce", "C_veg", "F_powder", "X_fert"]:
        cat_lines = sorted((lid, info) for lid, info in lines.items() if info["category"] == cat)
        if not cat_lines:
            continue
        cat_name = CATEGORY_DISPLAY[cat]
        out.append(f"# -- {cat_name} lines ({len(cat_lines)}) --")
        for lid, info in cat_lines:
            speed = CATEGORY_SPEED[cat]
            display_name = f"{cat_name}_{lid}"
            bom = build_workspace_bom(info["skus"], simple_bom, sku_set)

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

    # Virtual edges: source -> all storage nodes
    out.append("# -- Virtual edges: source -> storage nodes (transport_time=0) --")
    out.append('EDGES.append({')
    out.append('    "from_node": "source", "to_node": "raw_material_storage",')
    out.append('    "transfer_mode": TransferMode.BATCH,')
    out.append('    "batch_transport_time": 0.0, "batch_pallets": 1000,')
    out.append('})')
    out.append('EDGES.append({')
    out.append('    "from_node": "source", "to_node": "veg_raw_storage",')
    out.append('    "transfer_mode": TransferMode.BATCH,')
    out.append('    "batch_transport_time": 0.0, "batch_pallets": 1000,')
    out.append('})')
    out.append('EDGES.append({')
    out.append('    "from_node": "source", "to_node": "prep_storage_1",')
    out.append('    "transfer_mode": TransferMode.BATCH,')
    out.append('    "batch_transport_time": 0.0, "batch_pallets": 1000,')
    out.append('})')
    out.append('EDGES.append({')
    out.append('    "from_node": "source", "to_node": "prep_storage_2",')
    out.append('    "transfer_mode": TransferMode.BATCH,')
    out.append('    "batch_transport_time": 0.0, "batch_pallets": 1000,')
    out.append('})')
    out.append("")

    # Normal edges: raw storages -> prep storages (for raw materials in FERT assembly)
    out.append("# -- Normal edges: raw storages -> prep storages --")
    for raw_store in ["raw_material_storage", "veg_raw_storage"]:
        for prep_store in ["prep_storage_1", "prep_storage_2"]:
            out.append(f'EDGES.append({{')
            out.append(f'    "from_node": "{raw_store}", "to_node": "{prep_store}",')
            out.append(f'    "transfer_mode": TransferMode.BATCH,')
            out.append(f'    "batch_transport_time": 1.0, "batch_pallets": 1000,')
            out.append(f'}})')
    out.append("")

    # Normal edges: raw storages -> lineside
    for cat in ["J_sauce", "C_veg", "F_powder"]:
        cat_lines = sorted((lid, info) for lid, info in lines.items() if info["category"] == cat)
        if not cat_lines:
            continue
        cat_name = CATEGORY_DISPLAY[cat]
        upstream = CATEGORY_UPSTREAM[cat]
        out.append(f"# -- {cat_name}: {upstream} -> lineside (normal) --")
        for lid, info in cat_lines:
            out.append(f'EDGES.append({{')
            out.append(f'    "from_node": "{upstream}", "to_node": "lineside_{lid}",')
            out.append(f'    "transfer_mode": TransferMode.BATCH,')
            out.append(f'    "batch_transport_time": 1.0, "batch_pallets": 1000,')
            out.append(f'}})')
        out.append("")

    # Normal edges: prep_storage -> X lineside
    x_lines = sorted((lid, info) for lid, info in lines.items() if info["category"] == "X_fert")
    out.append("# -- 成品组装: prep_storage -> lineside (normal) --")
    for lid, info in x_lines:
        prep = prep_storage_for_x(lid)
        out.append(f'EDGES.append({{')
        out.append(f'    "from_node": "{prep}", "to_node": "lineside_{lid}",')
        out.append(f'    "transfer_mode": TransferMode.BATCH,')
        out.append(f'    "batch_transport_time": 1.0, "batch_pallets": 1000,')
        out.append(f'}})')
    out.append("")

    # Virtual edges: output -> wip storage
    out.append("# -- Virtual edges: output -> wip storage (transport_time=0) --")
    for cat in ["J_sauce", "F_powder"]:
        cat_lines = sorted((lid, info) for lid, info in lines.items() if info["category"] == cat)
        for lid, info in cat_lines:
            out.append(f'EDGES.append({{')
            out.append(f'    "from_node": "output_{lid}", "to_node": "wip_storage",')
            out.append(f'    "transfer_mode": TransferMode.BATCH,')
            out.append(f'    "batch_transport_time": 0.0, "batch_pallets": 1000,')
            out.append(f'}})')
    out.append("")

    c_lines = sorted((lid, info) for lid, info in lines.items() if info["category"] == "C_veg")
    out.append("# -- Virtual edges: output -> veg_wip_storage (transport_time=0) --")
    for lid, info in c_lines:
        out.append(f'EDGES.append({{')
        out.append(f'    "from_node": "output_{lid}", "to_node": "veg_wip_storage",')
        out.append(f'    "transfer_mode": TransferMode.BATCH,')
        out.append(f'    "batch_transport_time": 0.0, "batch_pallets": 1000,')
        out.append(f'}})')
    out.append("")

    # Virtual edges: wip storages -> prep storages
    out.append("# -- Virtual edges: wip storages -> prep storages (transport_time=0) --")
    for wip in ["wip_storage", "veg_wip_storage"]:
        for prep in ["prep_storage_1", "prep_storage_2"]:
            out.append(f'EDGES.append({{')
            out.append(f'    "from_node": "{wip}", "to_node": "{prep}",')
            out.append(f'    "transfer_mode": TransferMode.BATCH,')
            out.append(f'    "batch_transport_time": 0.0, "batch_pallets": 1000,')
            out.append(f'}})')
    out.append("")

    # Virtual edges: output -> fg_storage
    out.append("# -- Virtual edges: output -> fg_storage (transport_time=0) --")
    for lid, info in x_lines:
        out.append(f'EDGES.append({{')
        out.append(f'    "from_node": "output_{lid}", "to_node": "fg_storage",')
        out.append(f'    "transfer_mode": TransferMode.BATCH,')
        out.append(f'    "batch_transport_time": 0.0, "batch_pallets": 1000,')
        out.append(f'}})')
    out.append("")

    # Normal edge: fg_storage -> sink
    out.append("# -- Normal edge: fg_storage -> sink (transport_time=5) --")
    out.append('EDGES.append({')
    out.append('    "from_node": "fg_storage", "to_node": "sink",')
    out.append('    "transfer_mode": TransferMode.BATCH,')
    out.append('    "batch_transport_time": 5.0, "batch_pallets": 1000,')
    out.append('})')

    return "\n".join(out) + "\n"


def main():
    feas = load_feasibility()
    simple_bom = load_simple_bom()
    sauce_to_j = build_sauce_to_j_mapping()

    line_info = {}
    for line_id, skus in feas.items():
        cat = classify_line(line_id)
        if cat == "unknown":
            continue

        if cat == "J_sauce":
            valid_skus = filter_line_skus(line_id, cat, skus, sauce_to_j, simple_bom)
            line_info[line_id] = {
                "skus": valid_skus,
                "category": cat,
            }
            print(f"[TOPOLOGY] J line {line_id}: {len(valid_skus)} sauce packets", file=sys.stderr)
        else:
            valid_skus = filter_line_skus(line_id, cat, skus, sauce_to_j, simple_bom)
            line_info[line_id] = {
                "skus": valid_skus,
                "category": cat,
            }

    sku_df = pd.read_excel(SKUS_XLSX)
    sku_set: set[str] = set(sku_df["sku_id"].astype(str))
    print(f"[TOPOLOGY] SKU universe: {len(sku_set)}", file=sys.stderr)

    for cat in ["J_sauce", "C_veg", "F_powder", "X_fert"]:
        n = sum(1 for v in line_info.values() if v["category"] == cat)
        total_skus = sum(len(v["skus"]) for v in line_info.values() if v["category"] == cat)
        print(f"[TOPOLOGY]   {cat}: {n} lines, {total_skus} SKUs", file=sys.stderr)

    code = generate(line_info, simple_bom, sauce_to_j, sku_set)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(code, encoding="utf-8")

    n_nodes = code.count('"type"')
    n_edges = code.count('EDGES.append')
    print(f"[TOPOLOGY] Wrote {OUT_PATH}", file=sys.stderr)
    print(f"[TOPOLOGY]   Nodes: {n_nodes}", file=sys.stderr)
    print(f"[TOPOLOGY]   Edges: {n_edges}", file=sys.stderr)


if __name__ == "__main__":
    main()
