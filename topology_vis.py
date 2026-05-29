#!/usr/bin/env python3
"""
Factory Topology Visualizer

Imports a topology config module and generates a Mermaid flowchart.
Handles warehouse nodes, production nodes, source, and sink with proper labeling.
"""

import sys
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


def load_topology_module(module_path: str) -> Any:
    """Dynamically load a topology config Python file, handling relative imports."""
    path = Path(module_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Topology file not found: {module_path}")

    # The topology file lives inside a package (e.g. scenario/t_hangzhou1/plant_topology.py)
    # We need to load it as part of its package so relative imports work.
    # Strategy: add the *grandparent* of the file (e.g. scenario/) to sys.path,
    # then import it as scenario.t_hangzhou1.plant_topology

    # Determine package root: the directory containing the immediate parent of the file
    # e.g. for scenario/t_hangzhou1/plant_topology.py:
    #   file_dir = scenario/t_hangzhou1
    #   package_root = scenario
    #   package_name = t_hangzhou1
    file_dir = path.parent
    package_root = file_dir.parent
    package_name = file_dir.name
    module_name = path.stem
    full_qual_name = f"{package_name}.{module_name}"

    # Add package root to sys.path if not already there
    root_str = str(package_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # Ensure the package directory has an __init__.py (or is recognized as a namespace package)
    # Python 3.3+ supports implicit namespace packages, but let's be safe
    init_file = file_dir / "__init__.py"
    if not init_file.exists():
        init_file.touch()

    # Load the module via importlib
    spec = importlib.util.spec_from_file_location(
        full_qual_name,
        str(path),
        submodule_search_locations=None
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[full_qual_name] = module
    spec.loader.exec_module(module)
    return module


def escape_mermaid_id(node_id: str) -> str:
    """Escape node ID for Mermaid (replace hyphens, dots, etc. with underscores)."""
    safe = node_id.replace("-", "_").replace(".", "_").replace("/", "_")
    if safe and safe[0].isdigit():
        safe = "n" + safe
    return safe


def node_style(node_type: str) -> str:
    """Return Mermaid style class for a node type."""
    styles = {
        "source": ":::source",
        "sink": ":::sink",
        "warehouse": ":::warehouse",
        "production": ":::production",
    }
    return styles.get(node_type, "")


def generate_mermaid(module: Any, title: str = "Factory Topology") -> str:
    """Generate a Mermaid flowchart string from a loaded topology module."""
    nodes = getattr(module, "NODES", {})
    edges = getattr(module, "EDGES", [])

    lines = []
    lines.append("---")
    lines.append(f"title: {title}")
    lines.append("---")
    lines.append("flowchart LR")
    lines.append("")

    # Group nodes into logical subgraphs
    subgraphs = {
        "供应商": [],
        "原料与半成品": [],
        "酱包产线": [],
        "粉包产线": [],
        "菜包产线": [],
        "面线产线": [],
        "成品与发货": [],
    }
    assigned = set()

    for nid, info in nodes.items():
        ntype = info.get("type", "unknown")
        name = info.get("display_name", nid)
        safe_id = escape_mermaid_id(nid)

        if nid == "source":
            subgraphs["供应商"].append((safe_id, name, ntype))
            assigned.add(nid)
        elif nid == "raw_material_storage":
            subgraphs["原料与半成品"].append((safe_id, name, ntype))
            assigned.add(nid)
        elif nid == "WIP_storage":
            subgraphs["原料与半成品"].append((safe_id, name, ntype))
            assigned.add(nid)
        elif nid.startswith("lineside_sauce_") or nid.startswith("workstation_sauce_") or nid.startswith("output_sauce_"):
            subgraphs["酱包产线"].append((safe_id, name, ntype))
            assigned.add(nid)
        elif nid.startswith("lineside_powder_") or nid.startswith("workstation_powder_") or nid.startswith("output_powder_"):
            subgraphs["粉包产线"].append((safe_id, name, ntype))
            assigned.add(nid)
        elif nid.startswith("lineside_veg") or nid == "workstation_veg" or nid == "output_veg":
            subgraphs["菜包产线"].append((safe_id, name, ntype))
            assigned.add(nid)
        elif nid.startswith("main_storage_"):
            subgraphs["原料与半成品"].append((safe_id, name, ntype))
            assigned.add(nid)
        elif nid.startswith("lineside_noodle_") or nid.startswith("workstation_noodle_") or nid.startswith("output_noodle_"):
            subgraphs["面线产线"].append((safe_id, name, ntype))
            assigned.add(nid)
        elif nid == "fg_storage" or nid == "sink":
            subgraphs["成品与发货"].append((safe_id, name, ntype))
            assigned.add(nid)

    for nid, info in nodes.items():
        if nid not in assigned:
            ntype = info.get("type", "unknown")
            name = info.get("display_name", nid)
            safe_id = escape_mermaid_id(nid)
            subgraphs.setdefault("其他", []).append((safe_id, name, ntype))

    for sg_name, node_list in subgraphs.items():
        if not node_list:
            continue
        lines.append(f"    subgraph {sg_name}")
        for safe_id, name, ntype in node_list:
            style = node_style(ntype)
            lines.append(f'        {safe_id}["{name}"]{style}')
        lines.append("    end")
        lines.append("")

    for edge in edges:
        from_node = edge.get("from_node", "")
        to_node = edge.get("to_node", "")
        if from_node not in nodes or to_node not in nodes:
            continue

        safe_from = escape_mermaid_id(from_node)
        safe_to = escape_mermaid_id(to_node)

        mode = edge.get("transfer_mode", "")
        mode_label = str(mode).split(".")[-1] if hasattr(mode, "name") else str(mode)

        label_parts = [mode_label]
        if "batch_transport_time" in edge:
            label_parts.append(f"t={edge['batch_transport_time']}")
        if "batch_pallets" in edge:
            label_parts.append(f"bp={edge['batch_pallets']}")

        edge_label = "|" + ", ".join(label_parts) + "|" if label_parts else ""
        lines.append(f"    {safe_from} -->{edge_label} {safe_to}")

    lines.append("")
    lines.append("    classDef source fill:#90EE90,stroke:#228B22,stroke-width:2px")
    lines.append("    classDef sink fill:#FFB6C1,stroke:#DC143C,stroke-width:2px")
    lines.append("    classDef warehouse fill:#87CEEB,stroke:#1E90FF,stroke-width:2px")
    lines.append("    classDef production fill:#FFD700,stroke:#FF8C00,stroke-width:2px")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Visualize factory topology as Mermaid graph")
    parser.add_argument("topology_file", help="Path to the topology config Python file")
    parser.add_argument("-o", "--output", default="topology.mmd", help="Output Mermaid file path")
    parser.add_argument("-t", "--title", default="Factory Topology", help="Diagram title")
    parser.add_argument("--print", action="store_true", help="Print to stdout instead of writing file")
    args = parser.parse_args()

    module = load_topology_module(args.topology_file)
    mermaid = generate_mermaid(module, title=args.title)

    if args.print:
        print(mermaid)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(mermaid)
        print(f"Mermaid diagram written to: {args.output}")


if __name__ == "__main__":
    main()
