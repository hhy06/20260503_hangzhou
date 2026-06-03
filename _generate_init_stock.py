#!/usr/bin/env python3
"""Generate init_stock.py for a scenario based on topology analysis.

Usage:
    python _generate_init_stock.py scenario.<name>

The generator reads a scenario's config module, analyses the plant topology
(NODES + EDGES) and BOM data, then writes ``init_stock.py`` containing an
INIT_STOCK dict with evenly-split initial pallet quantities for every
warehouse node.
"""

import argparse
import importlib
import os


def generate(scenario_name: str) -> str:
    """Generate the ``init_stock.py`` source code for *scenario_name*.

    Args:
        scenario_name: Dotted module path, e.g. ``"scenario.ss_hangzhou0b"``.

    Returns:
        Complete text of the ``init_stock.py`` file.
    """
    # ------------------------------------------------------------------
    # 1.  Load scenario config
    # ------------------------------------------------------------------
    try:
        mod = importlib.import_module(f"{scenario_name}.config")
    except ImportError as exc:
        raise ImportError(
            f"Cannot import scenario module '{scenario_name}.config': {exc}"
        ) from exc

    NODES: dict = mod.NODES
    EDGES: list = getattr(mod, "EDGES", [])
    SKUS: dict = mod.SKUS

    scenario_short = scenario_name.split(".")[-1]

    # ------------------------------------------------------------------
    # 2.  Phase 1 — Seed SKU sets from BOMs
    # ------------------------------------------------------------------

    # Collect every SKU that is an output (key) of any production BOM
    all_production_outputs: set[str] = set()
    for node_cfg in NODES.values():
        if node_cfg.get("type") == "production":
            bom = node_cfg.get("bom", {})
            all_production_outputs.update(bom.keys())

    # Raw materials = anything in SKUS that is never produced
    raw_material_skus = set(SKUS.keys()) - all_production_outputs

    node_skus: dict[str, set[str]] = {}
    node_skus["source"] = set(raw_material_skus)

    for node_name, node_cfg in NODES.items():
        if node_cfg.get("type") != "production":
            continue

        bom = node_cfg.get("bom", {})
        upstream = node_cfg.get("upstream")
        downstream = node_cfg.get("downstream")

        # All input SKUs across every BOM entry of this workstation
        input_skus: set[str] = set()
        for bom_entry in bom.values():
            input_skus.update(bom_entry.get("inputs", {}).keys())

        output_skus = set(bom.keys())

        if upstream:
            node_skus.setdefault(upstream, set()).update(input_skus)
        if downstream:
            node_skus.setdefault(downstream, set()).update(output_skus)

    # ------------------------------------------------------------------
    # 3.  Phase 2 — Fixed-point propagation through edges
    # ------------------------------------------------------------------

    changed = True
    while changed:
        changed = False
        for edge in EDGES:
            from_node = edge["from_node"]
            to_node = edge["to_node"]
            to_node_cfg = NODES.get(to_node, {})

            if to_node_cfg.get("type") != "warehouse":
                continue
            # Do NOT propagate into lineside or output-buffer nodes
            # (they only receive their dedicated BOM-based seed)
            if to_node.startswith("lineside_") or to_node.startswith("output_"):
                continue

            from_skus = node_skus.get(from_node, set())
            if not from_skus:
                continue

            if to_node not in node_skus:
                node_skus[to_node] = set()
            before = len(node_skus[to_node])
            node_skus[to_node].update(from_skus)
            if len(node_skus[to_node]) > before:
                changed = True

    # ------------------------------------------------------------------
    # 4.  Phase 3 — Calculate quantities
    # ------------------------------------------------------------------

    init_stock: dict[str, dict[str, int]] = {}

    for node_name in NODES:
        node_cfg = NODES[node_name]
        if node_cfg.get("type") != "warehouse":
            continue

        stored_skus = node_skus.get(node_name, set())
        if not stored_skus:
            continue

        max_pallets = node_cfg.get("max_pallets")
        if max_pallets is None or max_pallets == 0:
            continue

        sorted_skus = sorted(stored_skus)

        if node_name.startswith("output_"):
            # Output buffers → zero initial stock
            init_stock[node_name] = {sku: 0 for sku in sorted_skus}
        else:
            even_split = max_pallets // len(sorted_skus)
            if even_split == 0:
                continue  # capacity too small for even one pallet per SKU
            node_entry: dict[str, int] = {}
            for sku in sorted_skus:
                ps = SKUS[sku].pallet_size
                if ps is None or ps <= 0:
                    raise ValueError(f"SKU {sku} missing pallet_size for init_stock")
                node_entry[sku] = even_split * ps
            init_stock[node_name] = node_entry

    # ------------------------------------------------------------------
    # 5.  Generate Python source
    # ------------------------------------------------------------------

    lines: list[str] = []
    lines.append(f'"""Initial stock levels for {scenario_short}.')
    lines.append("Auto-generated by _generate_init_stock.py.")
    lines.append('"""')
    lines.append("")
    lines.append("INIT_STOCK: dict[str, dict[str, int]] = {")

    node_keys = list(init_stock.keys())
    for ni, node_name in enumerate(node_keys):
        sku_dict = init_stock[node_name]
        sku_keys = list(sku_dict.keys())
        lines.append(f'    "{node_name}": {{')
        for si, sku in enumerate(sku_keys):
            value = sku_dict[sku]
            sep = "," if si < len(sku_keys) - 1 else ","
            lines.append(f'        "{sku}": {value}{sep}')
        sep = "," if ni < len(node_keys) - 1 else ","
        lines.append(f"    }}{sep}")

    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """CLI entry-point: parse arguments and write init_stock.py."""
    parser = argparse.ArgumentParser(
        description="Generate init_stock.py for a scenario"
    )
    parser.add_argument(
        "scenario",
        help="Scenario module path, e.g. scenario.ss_hangzhou0b",
    )
    args = parser.parse_args()

    source = generate(args.scenario)

    out_path = os.path.join(*(args.scenario.split(".") + ["init_stock.py"]))
    if os.path.exists(out_path):
        print(f"  [SKIP] {out_path} already exists — delete it first to regenerate")
        return

    with open(out_path, "w") as f:
        f.write(source)

    print(f"  [OK]  wrote {out_path}")


if __name__ == "__main__":
    main()
