"""Transform srw_hangzhou1 data into psp data.
Run from project root: python -m scenario.psp._transform_data
"""
from __future__ import annotations

import sys, math, re, importlib
from pathlib import Path
from collections import defaultdict

import pandas as pd

SCENARIO = Path(__file__).resolve().parents[0]

SKUS_XLSX = SCENARIO / "skus.xlsx"
BOM_XLSX = SCENARIO / "bom.xlsx"
DEMAND_XLSX = SCENARIO / "demand.xlsx"
TOPOLOGY_PY = SCENARIO / "plant_topology.py"

# Source Shenzhen data for types
SRC_DIR = Path.home() / "transf" / "temp" / "masterkong_large_康师傅"

# ── Load data ────────────────────────────────────────────────────
print("Loading data...")
skus = pd.read_excel(SKUS_XLSX, sheet_name="SKUS")
bom = pd.read_excel(BOM_XLSX, sheet_name="BOM")
demand = pd.read_excel(DEMAND_XLSX, sheet_name="DEMAND")
fg_seed = set(pd.read_csv(SRC_DIR / "key_sku_share_2025H2.csv")["物料"].astype(str))
bom_full = pd.read_csv(SRC_DIR / "bom_by_product.csv", encoding="utf-8-sig")

# Build SAP type mapping
all_types: dict[str, str] = {}
for _, r in pd.concat([
    bom_full[["产品物料号", "产品类型"]].rename(columns={"产品物料号": "sku_id", "产品类型": "type"}),
    bom_full[["投入物料号", "投入物料类型"]].rename(columns={"投入物料号": "sku_id", "投入物料类型": "type"}),
]).drop_duplicates(subset=["sku_id"]).iterrows():
    all_types[str(r["sku_id"])] = r["type"]

def get_t(sku: str) -> str:
    return all_types.get(sku, "?")

# ── Parse topology for SKU set ───────────────────────────────────
with open(TOPOLOGY_PY) as f:
    topo_content = f.read()
t_skus = set(re.findall(r"'([A-Za-z0-9]+)':\s*\{'inputs'", topo_content))

producers = set(bom["sku_id"].astype(str))
consumers = set(bom["material_id"].astype(str))
all_ids = set(skus["sku_id"].astype(str))

print(f"Loaded {len(skus)} SKUs, {len(bom)} BOM rows, {len(demand)} demand rows")

# ── Step A: Delete 102 isolated SKUs ────────────────────────────
isolated = all_ids - producers - consumers
print(f"\n[A] {len(isolated)} isolated SKUs (neither producer nor consumer)")

# ── Step B: 25 orphan WIP + 26 affected FGs ─────────────────────
orphan_wips = {
    "1101238","1101244","1101246","1101255",
    "1506AF4805","1506AF4806","1506AF8202","1506AF9901",
    "1506AK49","1506AK4902","1506AK9301",
    "1506AN2201","1506AN2301","1506AN2501","1506AN2601",
    "1506AN2701","1506AN2801","1506AN3101","1506AN3301","1506AN3401",
    "1506XR01","1506XR03","1513AY41B","1513AY42B","1515AK90",
}
affected_fgs: set[str] = set()
for ow in orphan_wips:
    affected_fgs.update(bom[bom["material_id"] == ow]["sku_id"].astype(str))
affected_fgs &= fg_seed

print(f"[B] {len(orphan_wips)} orphan WIPs, {len(affected_fgs)} affected FGs")

# ── Step C1: 54 BOM-but-no-workstation WIPs consumed by FGs ─────
c1_wips: set[str] = set()
c1_consumed_by_fg: dict[str, set[str]] = {}
for s in sorted(producers - t_skus):
    cons = set(bom[bom["material_id"] == s]["sku_id"].astype(str))
    cons_fg = cons & fg_seed
    if cons_fg and (s.startswith(("1101", "1503", "1513", "1517")) or s in orphan_wips):
        pass  # handled below
    if s in orphan_wips:
        continue
    cons_fg_only = cons - (producers - fg_seed)  # consumed by FGs or nothing
    if cons_fg:
        c1_wips.add(s)
        c1_consumed_by_fg[s] = cons_fg

print(f"[C1] {len(c1_wips)} WIPs consumed by FGs, no workstation")

# ── Step C2: 33 BOM-but-no-workstation WIPs consumed only by other WIPs ──
c2_wips: set[str] = set()
c2_consumed_by_wip: dict[str, set[str]] = {}
for s in sorted(producers - t_skus):
    if s in c1_wips or s in orphan_wips:
        continue
    cons = set(bom[bom["material_id"] == s]["sku_id"].astype(str))
    cons_fg = cons & fg_seed
    if not cons_fg:
        c2_wips.add(s)
        c2_consumed_by_wip[s] = cons

print(f"[C2] {len(c2_wips)} WIPs consumed only by other WIPs, no workstation")
for s in sorted(c2_wips):
    print(f"   {s} -> {c2_consumed_by_wip[s]}")

# ── Step D: 3 FG→FG bundle products ──────────────────────────────
fg_fg_pairs: list[tuple[str, str, float]] = []
for _, r in bom.iterrows():
    p, m = str(r["sku_id"]), str(r["material_id"])
    a = float(r["amount"])
    if p in fg_seed and m in fg_seed:
        fg_fg_pairs.append((p, m, a))
print(f"[D] {len(fg_fg_pairs)} FG→FG BOM pairs")

# ──────────────────────────────────────────────────────────────────
# Build delete sets
# ──────────────────────────────────────────────────────────────────
to_delete_skus: set[str] = set()

# A: isolated
to_delete_skus.update(isolated)

# B: orphan WIPs + affected FGs
to_delete_skus.update(orphan_wips)
to_delete_skus.update(affected_fgs)

print(f"\nTotal SKUs to delete directly: {len(to_delete_skus)}")

# SKUs to keep for now (C1, C2, and all FG→FG sub-FGs stay)
keep_mask = ~skus["sku_id"].astype(str).isin(to_delete_skus)
skus_clean = skus[keep_mask].copy()
print(f"SKUs after initial delete: {len(skus_clean)}")

# ──────────────────────────────────────────────────────────────────
# BOM transformation
# ──────────────────────────────────────────────────────────────────
# Build lookup: bom_dict[prod_id] = {mat_id: amount}
bom_dict: dict[str, dict[str, float]] = defaultdict(dict)
for _, r in bom.iterrows():
    pid = str(r["sku_id"])
    mid = str(r["material_id"])
    amt = float(r["amount"])
    if pid in to_delete_skus or mid in to_delete_skus:
        continue
    bom_dict[pid][mid] = bom_dict[pid].get(mid, 0) + amt

def multiply_bom(bom_input: dict[str, float], factor: float) -> dict[str, float]:
    return {k: round(v * factor, 8) for k, v in bom_input.items()}

def add_bom(target: dict[str, float], source: dict[str, float]):
    for k, v in source.items():
        target[k] = round(target.get(k, 0) + v, 8)

# ── Step C2→C1→FG: multi-level flattening ──
# First level: inline C2 into C1 (update C1's BOM inputs)
print(f"\n[C2→C1] Flattening {len(c2_wips)} C2 WIPs into C1 WIPs...")
c2_flattened_count = 0
for c2 in sorted(c2_wips):
    if c2 not in bom_dict:
        continue
    c2_inputs = bom_dict.pop(c2, {})
    consumers_of_c2 = set(bom[bom["material_id"] == c2]["sku_id"].astype(str))
    for consumer in consumers_of_c2:
        if consumer in to_delete_skus:
            continue
        if consumer not in bom_dict:
            continue
        # Check if consumer uses this c2
        if c2 in bom_dict[consumer]:
            qty = bom_dict[consumer].pop(c2)
            # Add c2's inputs to consumer's BOM, scaled by qty
            add_bom(bom_dict[consumer], multiply_bom(c2_inputs, qty))
            c2_flattened_count += 1

# Second level: inline C1 into FG (update FG's BOM inputs)
print(f"[C1→FG] Flattening {len(c1_wips)} C1 WIPs into FGs...")
c1_flattened_count = 0
for c1 in sorted(c1_wips):
    if c1 in to_delete_skus:
        continue
    if c1 not in bom_dict:
        continue
    c1_inputs = bom_dict.pop(c1, {})
    consumers_of_c1 = c1_consumed_by_fg.get(c1, set())
    for consumer in consumers_of_c1:
        if consumer in to_delete_skus:
            continue
        if consumer not in bom_dict:
            continue
        if c1 in bom_dict[consumer]:
            qty = bom_dict[consumer].pop(c1)
            add_bom(bom_dict[consumer], multiply_bom(c1_inputs, qty))
            c1_flattened_count += 1

# ── Step D: FG→FG flattening ──
print(f"[D→FG] Flattening {len(fg_fg_pairs)} FG→FG bundles...")
for parent, child, amt in fg_fg_pairs:
    if parent in to_delete_skus or child in to_delete_skus:
        continue
    if parent not in bom_dict or child not in bom_dict:
        continue
    child_inputs = bom_dict.get(child, {})
    if child in bom_dict[parent]:
        bom_dict[parent].pop(child)
    add_bom(bom_dict[parent], multiply_bom(child_inputs, amt))

# ── Clean BOM: remove entries for deleted SKUs ──
# Rebuild bom_dict into a DataFrame
new_bom_rows: list[dict] = []
for pid, mats in sorted(bom_dict.items()):
    for mid, amt in sorted(mats.items()):
        if pid in to_delete_skus or mid in to_delete_skus:
            continue
        new_bom_rows.append({"sku_id": pid, "material_id": mid, "amount": amt})

new_bom = pd.DataFrame(new_bom_rows, columns=["sku_id", "material_id", "amount"])
print(f"New BOM rows: {len(new_bom)} (was {len(bom)})")

# ──────────────────────────────────────────────────────────────────
# Clean demand: remove deleted FGs ─────────────────────────────────
fg_demand_mask = ~demand["sku"].astype(str).isin(to_delete_skus)
demand_clean = demand[fg_demand_mask].copy().reset_index(drop=True)
print(f"New demand rows: {len(demand_clean)} (was {len(demand)})")

# ──────────────────────────────────────────────────────────────────
# Clean topology: remove workstation entries for deleted SKUs
# ──────────────────────────────────────────────────────────────────
def remove_topo_skus(content: str, skus_to_remove: set[str]) -> str:
    """Remove deleted SKU entries from workstation BOM dicts."""
    lines = content.split("\n")
    out_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if this line starts a BOM entry for a deleted SKU
        stripped = line.strip()
        skip_this = False
        for sku in skus_to_remove:
            pattern = f"'{sku}':"
            if pattern in stripped and ("{" in stripped or "'inputs'" in stripped or i+1 < len(lines)):
                # This is a BOM key for a deleted SKU - skip until next top-level key or closing }
                skip_this = True
                break
        if skip_this:
            # Skip lines until we find the next top-level key or end of bom dict
            brace_depth = stripped.count("{") - stripped.count("}")
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                brace_depth += s.count("{") - s.count("}")
                if brace_depth <= 0 and i < len(lines):
                    # Also check for next key at same level
                    if any(f"'{sk}'" in s for sk in skus_to_remove):
                        pass  # continue skipping
                    elif brace_depth <= 0:
                        break
                i += 1
            continue
        out_lines.append(line)
        i += 1
    return "\n".join(out_lines)

# Simpler approach: just regenerate topology with the new SKU set
# But instead, let's just modify the existing one
# Find all SKUs in the topology that should be removed
all_topo_skus_to_remove = set()
for s in to_delete_skus | orphan_wips | c1_wips | c2_wips:
    if s in t_skus:
        all_topo_skus_to_remove.add(s)

# Also remove WIPs that were flattened (C1, C2)
for s in c1_wips | c2_wips:
    if s in t_skus:
        all_topo_skus_to_remove.add(s)

print(f"Topology SKUs to remove: {len(all_topo_skus_to_remove)}")

# ──────────────────────────────────────────────────────────────────
# Clean skus.xlsx: remove all deleted + flattened WIPs
# ──────────────────────────────────────────────────────────────────
skus_final_remove = to_delete_skus | orphan_wips | c1_wips | c2_wips
keep = ~skus["sku_id"].astype(str).isin(skus_final_remove)
skus_final = skus[keep].copy().reset_index(drop=True)
print(f"Final SKU count: {len(skus_final)} (was {len(skus)})")

# ── Add type column to skus ──
skus_final["type"] = skus_final["sku_id"].astype(str).map(all_types).fillna("RAW")

# ──────────────────────────────────────────────────────────────────
# Write outputs
# ──────────────────────────────────────────────────────────────────
BACKUP = SCENARIO / "_backup"
BACKUP.mkdir(exist_ok=True)

# Backup originals
import shutil
for f in [SKUS_XLSX, BOM_XLSX, DEMAND_XLSX, TOPOLOGY_PY]:
    shutil.copy2(f, BACKUP / f.name)

# Write new files
with pd.ExcelWriter(SKUS_XLSX, engine="openpyxl") as writer:
    skus_final.to_excel(writer, sheet_name="SKUS", index=False)
print(f"[WRITE] {SKUS_XLSX}")

with pd.ExcelWriter(BOM_XLSX, engine="openpyxl") as writer:
    new_bom.to_excel(writer, sheet_name="BOM", index=False)
print(f"[WRITE] {BOM_XLSX}")

with pd.ExcelWriter(DEMAND_XLSX, engine="openpyxl") as writer:
    demand_clean.to_excel(writer, sheet_name="DEMAND", index=False)
print(f"[WRITE] {DEMAND_XLSX}")

# ──────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  TRANSFORMATION SUMMARY")
print(f"{'='*60}")
print(f"  SKUs: {len(skus)} → {len(skus_final)} (removed {len(skus)-len(skus_final)})")
print(f"  BOM rows: {len(bom)} → {len(new_bom)}")
print(f"  Demand rows: {len(demand)} → {len(demand_clean)}")
print(f"  Topology SKUs removed: {len(all_topo_skus_to_remove)}")
print(f"  C2→C1 flattens: {c2_flattened_count}")
print(f"  C1→FG flattens: {c1_flattened_count}")
print(f"  FG→FG flattens: {len(fg_fg_pairs)}")
print(f"{'='*60}")
print(f"  Backups saved to {BACKUP}")
print(f"{'='*60}")
