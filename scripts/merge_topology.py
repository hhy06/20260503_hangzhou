"""Merge per-line lineside/output nodes into per-type nodes in plant_topology.py.

Usage: python scripts/merge_topology.py
"""

import re
import sys
from pathlib import Path


# Line ID → group type mapping
def line_id_to_type(lid: str) -> str | None:
    """Map a line_id to its merged group type."""
    # J group (sauce): J01-J12, J0A, J0B, J1A, J1B, J9A, J9B, ZJ1
    if lid.startswith("J") or lid == "ZJ1":
        return "J"
    # F group (powder): F01-F12, FB1, FB2, H01-H03, DF1, ZL1
    if (lid.startswith("F") or lid.startswith("FB") or lid.startswith("H")
            or lid.startswith("DF") or lid.startswith("ZL")):
        return "F"
    # C group (veg): C01-C12, DC1-DC6, XC1, XC2
    if lid.startswith("C") or lid.startswith("DC") or lid.startswith("XC"):
        return "C"
    # X1 group (FG prep_1): X00-X08
    if lid.startswith("X"):
        num_str = lid[1:]
        if num_str.isdigit():
            num = int(num_str)
            if num <= 8:
                return "X1"
            else:
                return "X2"
    return None


def get_merged_display_name(ltype: str) -> str:
    names = {"J": "酱包", "F": "粉包", "C": "菜包", "X1": "成品1", "X2": "成品2"}
    return names.get(ltype, ltype)


def transform_file(filepath: Path):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # First pass: identify line_ids and their types
    line_ids: set[str] = set()
    line_type: dict[str, str] = {}
    for line in lines:
        m = re.match(r'NODES\["workstation_(\w+)"\] = {', line)
        if m:
            lid = m.group(1)
            line_ids.add(lid)
            lt = line_id_to_type(lid)
            if lt:
                line_type[lid] = lt

    merged_types = sorted(set(line_type.values()))

    # Process lines
    out_lines: list[str] = []
    i = 0
    pool_section_done = False
    merged_nodes_added = False

    while i < len(lines):
        line = lines[i]

        # Check for lineside node definition — skip until closing }
        m = re.match(r'NODES\["lineside_(\w+)"\] = {', line)
        if m and m.group(1) in line_ids:
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('NODES[') and not lines[i].strip().startswith('#'):
                if lines[i].strip() == '}':
                    i += 1
                    break
                i += 1
            continue

        # Check for output node definition — skip until closing }
        m = re.match(r'NODES\["output_(\w+)"\] = {', line)
        if m and m.group(1) in line_ids:
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('NODES[') and not lines[i].strip().startswith('#'):
                if lines[i].strip() == '}':
                    i += 1
                    break
                i += 1
            continue

        # Check for workstation node — update upstream/downstream
        m = re.match(r'(NODES\["workstation_(\w+)"\] = {)', line)
        if m:
            lid = m.group(2)
            lt = line_type.get(lid)
            out_lines.append(line)  # keep the opening line
            i += 1
            # Process the body lines of the workstation
            while i < len(lines) and not lines[i].startswith("NODES[") and not lines[i].startswith("#"):
                stripped = lines[i]
                if stripped.strip() == '}':
                    out_lines.append(stripped)
                    i += 1
                    break
                if lt:
                    # Replace upstream and downstream references
                    if '"upstream"' in stripped:
                        stripped = re.sub(
                            r'"upstream": "lineside_\w+"',
                            f'"upstream": "lineside_{lt}"',
                            stripped,
                        )
                    if '"downstream"' in stripped:
                        stripped = re.sub(
                            r'"downstream": "output_\w+"',
                            f'"downstream": "output_{lt}"',
                            stripped,
                        )
                out_lines.append(stripped)
                i += 1
            continue

        # Check for EDGES — replace lineside/output references
        if line.strip().startswith('EDGES.append({'):
            # Collect the full edge block
            edge_lines = [line]
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('EDGES.append({') and not lines[i].strip().startswith('#') and not lines[i].strip().startswith('NODES['):
                edge_lines.append(lines[i])
                if lines[i].strip().endswith('})'):
                    i += 1
                    break
                i += 1
            # Transform the edge block
            transformed = False
            new_edge = []
            for el in edge_lines:
                # Replace per-line node references with merged ones
                new_el = el
                for lid in line_ids:
                    lt = line_type.get(lid)
                    if not lt:
                        continue
                    # Replace "lineside_{lid}" → "lineside_{lt}" in edges
                    new_el = new_el.replace(f'"lineside_{lid}"', f'"lineside_{lt}"')
                    # Replace "output_{lid}" → "output_{lt}" in edges
                    new_el = new_el.replace(f'"output_{lid}"', f'"output_{lt}"')
                new_edge.append(new_el)
                if new_el != el:
                    transformed = True
            # Only keep edges that still have distinct from/to (skip duplicates)
            if transformed:
                edge_key = tuple(new_edge)
                # Deduplicate: keep only if we haven't seen this exact edge
                if edge_key not in _seen_edges:
                    _seen_edges.add(edge_key)
                    out_lines.extend(new_edge)
            else:
                _seen_edges.add(tuple(edge_lines))
                out_lines.extend(edge_lines)
            continue

        # Detect end of pool section (after first comment line with # --)
        if not pool_section_done and line.strip().startswith("# --") and "lines" in line:
            pool_section_done = True
            out_lines.append(line)

            # Add merged lineside and output nodes after pool section
            if not merged_nodes_added:
                out_lines.append("\n")
                for lt in merged_types:
                    dn = get_merged_display_name(lt)
                    out_lines.append(f'NODES["lineside_{lt}"] = {{\n')
                    out_lines.append(f'    "type": "warehouse", "max_pallets": 500,\n')
                    out_lines.append(f'    "display_name": "{dn}_线边仓"}}\n')
                out_lines.append("\n")
                for lt in merged_types:
                    dn = get_merged_display_name(lt)
                    out_lines.append(f'NODES["output_{lt}"] = {{\n')
                    out_lines.append(f'    "type": "warehouse", "max_pallets": 500,\n')
                    out_lines.append(f'    "display_name": "{dn}_产出缓存"}}\n')
                out_lines.append("\n")
                merged_nodes_added = True
            i += 1
            continue

        out_lines.append(line)
        i += 1

    # Write output
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(out_lines)

    print(f"Transformed {filepath}")
    print(f"  Line IDs found: {len(line_ids)}")
    type_counts = {}
    for lid, lt in line_type.items():
        type_counts[lt] = type_counts.get(lt, 0) + 1
    for lt in sorted(type_counts):
        print(f"  {lt}: {type_counts[lt]} lines")


if __name__ == "__main__":
    _seen_edges: set[tuple] = set()
    psp_path = Path(__file__).resolve().parent.parent / "scenario" / "psp" / "plant_topology.py"
    transform_file(psp_path)