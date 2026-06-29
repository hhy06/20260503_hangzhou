"""Transform srw_hangzhou1 → psp data. Run from project root.
    python -m scenario.psp._transform
"""
from __future__ import annotations
import sys, re, shutil
from pathlib import Path
from collections import defaultdict
import pandas as pd

HERE = Path(__file__).resolve().parents[0]
SRC = Path.home() / "transf" / "temp" / "masterkong_large_康师傅"
BACKUP = HERE / "_backup"

# ── SKU sets to delete ──────────────────────────────────────────
ISOLATED_A3_HALB = {
    "15N1441O","15N1503C","15N1503O","15N1508OJ","15N151004O",
    "15N1522O","15N1522OJ","15N1523O","15N1523OC","15N1560O",
    "15N1569O","15N1569O1","15N1598O","15N1598OL","15N1604C",
    "15N1604O","15N1604OL","15N1606O","15N1607OJ","15N1607OY",
    "15N1616OJ","15N1616OY","15N1617O","15N1619O","15N1620OJ",
    "15N1620OY","15N1632OJ","15N1633O","15N1636OJ","15N1643O",
    "15N1655O","15N1655O1","15N1705O","15N1714O","15N1722OG",
    "15N1956T","15N1958O","15N1959OJ","15N1959OY","15N1960OJ",
    "15N1960OY","15N1961O","15N1962OJ","15N1962OY","15N2627O",
    "15N2650T","15N2907O","15N292010O","15N2920O","15N292208O",
    "15N292208OY","15N2931O","15N2937O","15N2938O","15N2941T",
    "15N2943O","15N2944C","15N2944O","15N2944Z","15N295001O",
    "15N2950O","15N2955O","15N2956O","15N2957O","15N356001OD",
    "15N3560OD","15N3563OJ","15N3564O","15N3564O01","15N3567C",
    "15N3567O","15N3574OJ","15N3574OY","15N393202O","15N4206O",
    "15N4206T","15N4208O","15N4210OJ","15N4210OY","15N5110OJ",
    "15N5306O","15N5310OJ","15N5310OY","15N5311OJ","15N5314OJ",
    "15N5316O","15N5317O","15N5816C","15N5816O","15N5816T",
    "15N5829OJ","15N7005O","15N9101O1","15N9105O",
}
ISOLATED_A1_FG = {"17AN340671H","17AV511201H","17AW543001H"}
ISOLATED_A2_RAW = {"11008399B","11009179","1116059","1205AT9701","1208AT971201AH"}
ISOLATED = ISOLATED_A3_HALB | ISOLATED_A1_FG | ISOLATED_A2_RAW

ORPHAN_WIPS = {
    "1101238","1101244","1101246","1101255",
    "1506AF4805","1506AF4806","1506AF8202","1506AF9901",
    "1506AK49","1506AK4902","1506AK9301",
    "1506AN2201","1506AN2301","1506AN2501","1506AN2601",
    "1506AN2701","1506AN2801","1506AN3101","1506AN3301","1506AN3401",
    "1506XR01","1506XR03","1513AY41B","1513AY42B","1515AK90",
}
AFFECTED_FGS = {
    "17AF480426H","17AF480603H","17AF821200H","17AF831200H",
    "17AF971201H","17AF991200H","17AK901600H","17AK911601H",
    "17AK921600H","17AK930600H","17AN220600H","17AN230400H",
    "17AN251201H","17AN261201H","17AN270500H","17AN281600H",
    "17AN310600H","17AN310671H","17AN310672H","17AN330600H",
    "17AN330671H","17AN340600H",
    "17AY411200H","17AY411601H","17AY421200H","17AY421601H",
}

# C1: BOM-but-no-workstation WIPs consumed by FGs
C1_WIPS = {
    "1101237","1101239","1101251","1101252","1101253","1101254",
    "1101260","1101261","1101263","1101264","1101265","1101266","1101271",
    "1503AN05B","1503AN09B","1503AN10B","1503AN61B","1503AT88B",
    "1503AV02B","1503AV43B","1503AV55B","1503AZ16B","1503AZ2601B",
    "1513AD87B","1513AF2001B","1513AF25B",
    "1513AF4801B","1513AF4803B","1513AF4804B","1513AF64B",
    "1513AF97B","1513AF99B","1513AH26B","1513AK78B",
    "1513AK8301B","1513AK83B1","1513AK9101B","1513AK91B","1513AK93B",
    "1513AN22B","1513AN26B","1513AN31B","1513AN33B","1513AN34B",
    "1513AS59B","1513AS9309B","1513AT45B","1513AT72B",
    "1513AV48B","1513AV51B","1513AX02B","1513AX03B",
    "1513AY12B","1513AY19BL","1513AY40B","1513AY44B",
    "1517AF28B",
}

# C2: BOM-but-no-workstation WIPs consumed by other WIPs (not by FGs directly)
C2_WIPS = {
    "15N1632OY","15N1636OY","15N1956Y","15N1962C",
    "15N2626O","15N2630O","15N2633O",
    "15N2951OY","15N2951Z","15N356001O","15N3560O",
    "15N3931O","15N4209O","15N5109C","15N5109O","15N5110OY",
    "15N5311OY","15N5314OY","15N5318O","15N535601",
    "15N580801OJ","15N580801OY","15N582001","15N5820T",
    "15N5820TJ","15N5820TY","15N5829O1","15N5829OY",
    "15N9107O1","15N9201O1",
}

ALL_DEL = ISOLATED | ORPHAN_WIPS | AFFECTED_FGS | C1_WIPS | C2_WIPS
ALL_WIP_DEL = C1_WIPS | C2_WIPS  # WIPs to be absorbed, not just removed

print(f"SKUs to delete: {len(ALL_DEL)}")
print(f"  Isolated: {len(ISOLATED)}")
print(f"  Orphan WIPs: {len(ORPHAN_WIPS)}")
print(f"  Affected FGs: {len(AFFECTED_FGS)}")
print(f"  C1 WIPs (flatten into FG): {len(C1_WIPS)}")
print(f"  C2 WIPs (flatten into WIP): {len(C2_WIPS)}")

# ── Load ─────────────────────────────────────────────────────────
skus   = pd.read_excel(HERE / "skus.xlsx", sheet_name="SKUS")
bom    = pd.read_excel(HERE / "bom.xlsx", sheet_name="BOM")
demand = pd.read_excel(HERE / "demand.xlsx", sheet_name="DEMAND")

fg_seed = set(pd.read_csv(SRC / "key_sku_share_2025H2.csv")["物料"].astype(str))

# SAP types
bom_full = pd.read_csv(SRC / "bom_by_product.csv", encoding="utf-8-sig")
all_types: dict[str, str] = {}
for _, r in pd.concat([
    bom_full[["产品物料号","产品类型"]].rename(columns={"产品物料号":"sku_id","产品类型":"type"}),
    bom_full[["投入物料号","投入物料类型"]].rename(columns={"投入物料号":"sku_id","投入物料类型":"type"}),
]).drop_duplicates(subset=["sku_id"]).iterrows():
    all_types[str(r["sku_id"])] = r["type"]

# ── Build in-memory BOM dict (include ALL entries, even for deleted SKUs) ──
bom_dict: dict[str, dict[str, float]] = defaultdict(dict)
for _, r in bom.iterrows():
    pid, mid, amt = str(r["sku_id"]), str(r["material_id"]), float(r["amount"])
    bom_dict[pid][mid] = bom_dict[pid].get(mid, 0) + amt

def mul_bom(inp: dict, f: float) -> dict:
    return {k: round(v * f, 10) for k, v in inp.items()}
def add_bom(tgt: dict, src: dict):
    for k, v in src.items():
        tgt[k] = round(tgt.get(k, 0) + v, 10)

# ── Step 1: C2 → inline into their consumers (which are WIPs with workstations) ──
c2_count = 0
for c2 in sorted(C2_WIPS):
    if c2 not in bom_dict:
        continue
    c2_inputs = bom_dict.pop(c2)
    # Find all consumers (from original BOM data, not bom_dict which may be missing some)
    consumers = set(bom[bom["material_id"] == c2]["sku_id"].astype(str))
    for cons in consumers:
        if cons in ALL_DEL:
            # Consumer will be deleted too, no need to inline
            continue
        if cons not in bom_dict:
            continue
        if c2 not in bom_dict[cons]:
            continue
        qty = bom_dict[cons].pop(c2)
        add_bom(bom_dict[cons], mul_bom(c2_inputs, qty))
        c2_count += 1
print(f"  C2→WIP flattens: {c2_count}")

# ── Step 2: C1 → inline into their consuming FGs ──
c1_count = 0
for c1 in sorted(C1_WIPS):
    if c1 not in bom_dict:
        continue
    c1_inputs = bom_dict.pop(c1)
    consumers = set(bom[bom["material_id"] == c1]["sku_id"].astype(str))
    for cons in consumers:
        if cons in ALL_DEL:
            continue
        if cons not in bom_dict:
            continue
        if c1 not in bom_dict[cons]:
            continue
        qty = bom_dict[cons].pop(c1)
        add_bom(bom_dict[cons], mul_bom(c1_inputs, qty))
        c1_count += 1
print(f"  C1→FG flattens: {c1_count}")

# ── Step 3: FG→FG bundle flattening ──
FG_FG = [("1735111226H","17AT581204H",0.002934),
         ("17AJ281223H","17AX141200H",0.002468),
         ("17AT131224H","17AT961261H",0.011476)]
for parent, child, amt in FG_FG:
    if parent in ALL_DEL or child in ALL_DEL:
        continue
    if parent not in bom_dict or child not in bom_dict:
        continue
    child_inputs = bom_dict.get(child, {})
    if child in bom_dict[parent]:
        bom_dict[parent].pop(child)
    add_bom(bom_dict[parent], mul_bom(child_inputs, amt))

print(f"  FG→FG flattens: {len(FG_FG)}")

# ── Build output BOM (filter out ALL_DEL entries) ──
new_bom_rows = []
for pid in sorted(bom_dict):
    if pid in ALL_DEL:
        continue
    for mid in sorted(bom_dict[pid]):
        if mid in ALL_DEL:
            continue
        new_bom_rows.append({"sku_id": pid, "material_id": mid, "amount": bom_dict[pid][mid]})
new_bom = pd.DataFrame(new_bom_rows, columns=["sku_id","material_id","amount"])

# ── Output SKUs ──────────────────────────────────────────────────
mask = ~skus["sku_id"].astype(str).isin(ALL_DEL)
new_skus = skus[mask].copy().reset_index(drop=True)
new_skus["type"] = new_skus["sku_id"].astype(str).map(all_types).fillna("RAW")

# ── Output Demand ────────────────────────────────────────────────
dmask = ~demand["sku"].astype(str).isin(ALL_DEL)
new_demand = demand[dmask].copy().reset_index(drop=True)
print(f"  Remaining FG SKUs with demand: {new_demand['sku'].nunique()}")

# ── Output Init Stock & Safe Stock ──────────────────────────────
init_stock = pd.read_excel(HERE / "init_stock.xlsx", sheet_name="INIT_STOCK")
imask = ~init_stock["sku"].astype(str).isin(ALL_DEL)
new_init = init_stock[imask].copy().reset_index(drop=True)
print(f"init_stock.xlsx: {len(new_init)} rows (removed {len(init_stock)-len(new_init)})")

safe_stock = pd.read_excel(HERE / "safe_stock.xlsx", sheet_name="SAFE_STOCK")
smask = ~safe_stock["sku"].astype(str).isin(ALL_DEL)
new_safe = safe_stock[smask].copy().reset_index(drop=True)
print(f"safe_stock.xlsx: {len(new_safe)} rows (removed {len(safe_stock)-len(new_safe)})")

# ── Topology: remove ALL deleted SKUs from BOM dicts ────────────
with open(HERE / "plant_topology.py") as f:
    topo = f.read()

import re

def remove_skus_from_topo(content: str, skus: set[str]) -> str:
    # 1. Remove full entries: 'SKU': {'inputs': {...}, 'speed': N, 'lead_time': N}
    for sku in sorted(skus, key=len, reverse=True):
        esc = re.escape(sku)
        pat = re.compile(
            r"'" + esc + r"':\s*\{'inputs':\s*\{[^}]*\},\s*'speed':\s*\d+(?:\.\d+)?,\s*'lead_time':\s*\d+(?:\.\d+)?\},?\s*"
        )
        content = pat.sub('', content)

    # 2. Remove simple input entries: 'SKU': number
    for sku in sorted(skus, key=len, reverse=True):
        esc = re.escape(sku)
        pat = re.compile(
            r"'" + esc + r"':\s*-?\d+(?:\.\d+)?(?:e[+-]?\d+)?,?\s*"
        )
        content = pat.sub('', content)

    # 3. Clean up artifacts from removals
    content = re.sub(r",\s*,", ",", content)       # double commas
    content = re.sub(r",\s*\}", "}", content)       # trailing comma before }
    content = re.sub(r"\{\s*,", "{", content)       # leading comma after {
    content = re.sub(r"\{\s*,\s*\}", "{}", content) # empty dicts from removals
    return content

topo = remove_skus_from_topo(topo, ALL_DEL)

# ── Write outputs ────────────────────────────────────────────────
BACKUP.mkdir(exist_ok=True)
for fn in ["skus.xlsx","bom.xlsx","demand.xlsx","init_stock.xlsx","safe_stock.xlsx","plant_topology.py"]:
    shutil.copy2(HERE / fn, BACKUP / fn)

with pd.ExcelWriter(HERE / "skus.xlsx", engine="openpyxl") as w:
    new_skus.to_excel(w, sheet_name="SKUS", index=False)
print(f"skus.xlsx: {len(new_skus)} SKUs")

with pd.ExcelWriter(HERE / "bom.xlsx", engine="openpyxl") as w:
    new_bom.to_excel(w, sheet_name="BOM", index=False)
print(f"bom.xlsx: {len(new_bom)} rows")

with pd.ExcelWriter(HERE / "demand.xlsx", engine="openpyxl") as w:
    new_demand.to_excel(w, sheet_name="DEMAND", index=False)
print(f"demand.xlsx: {len(new_demand)} rows")

with pd.ExcelWriter(HERE / "init_stock.xlsx", engine="openpyxl") as w:
    new_init.to_excel(w, sheet_name="INIT_STOCK", index=False)
print(f"init_stock.xlsx: {len(new_init)} rows")

with pd.ExcelWriter(HERE / "safe_stock.xlsx", engine="openpyxl") as w:
    new_safe.to_excel(w, sheet_name="SAFE_STOCK", index=False)
print(f"safe_stock.xlsx: {len(new_safe)} rows")

with open(HERE / "plant_topology.py", "w") as f:
    f.write(topo)
print(f"plant_topology.py: updated")

# ── Verify ────────────────────────────────────────────────────────
print(f"\n{'='*50}\nVERIFICATION\n{'='*50}")
v_skus = pd.read_excel(HERE / "skus.xlsx", sheet_name="SKUS")
v_bom  = pd.read_excel(HERE / "bom.xlsx", sheet_name="BOM")
v_dem  = pd.read_excel(HERE / "demand.xlsx", sheet_name="DEMAND")
v_init = pd.read_excel(HERE / "init_stock.xlsx", sheet_name="INIT_STOCK")
v_safe = pd.read_excel(HERE / "safe_stock.xlsx", sheet_name="SAFE_STOCK")
print(f"SKUs:   {len(skus)} → {len(v_skus)}")
print(f"BOM:    {len(bom)} → {len(v_bom)}")
print(f"Demand: {len(demand)} → {len(v_dem)}")
print(f"Init:   {len(init_stock)} → {len(v_init)}")
print(f"Safe:   {len(safe_stock)} → {len(v_safe)}")

dels_in_skus = ALL_DEL & set(v_skus["sku_id"].astype(str))
dels_in_bom  = ALL_DEL & (set(v_bom["sku_id"].astype(str)) | set(v_bom["material_id"].astype(str)))
dels_in_dem  = ALL_DEL & set(v_dem["sku"].astype(str))
dels_in_init = ALL_DEL & set(v_init["sku"].astype(str))
dels_in_safe = ALL_DEL & set(v_safe["sku"].astype(str))

errors = []
if dels_in_skus: errors.append(f"skus.xlsx: {dels_in_skus}")
if dels_in_bom:  errors.append(f"BOM: {dels_in_bom}")
if dels_in_dem:  errors.append(f"demand: {dels_in_dem}")
if dels_in_init: errors.append(f"init_stock.xlsx: {dels_in_init}")
if dels_in_safe: errors.append(f"safe_stock.xlsx: {dels_in_safe}")
if errors:
    print(f"\nERRORS: {errors}")
else:
    print("\nSUCCESS: No deleted SKUs remain in any file")

# Check topology is parseable
try:
    with open(HERE / "plant_topology.py") as f:
        c = f.read()
    # Verify no deleted SKUs remain in topology
    dels_in_topo = [s for s in sorted(ALL_DEL) if f"'{s}':" in c]
    if dels_in_topo:
        print(f"WARNING: {len(dels_in_topo)} deleted SKUs still in topology!")
        for s in dels_in_topo[:10]:
            print(f"  {s}")
    exec(compile(c, "plant_topology.py", "exec"), {"__builtins__": __builtins__})
except Exception as e:
    print(f"Topology error: {e}")

print(f"\nType distribution:\n{v_skus['type'].value_counts().to_string()}")
print(f"\nBackup: {BACKUP}")
