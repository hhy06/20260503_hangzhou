"""Derive material procurement orders from FG and WIP plans.

Two sources of procurement:
1. WIP BOM: raw/pack inputs needed to produce planned WIP (from J/C/F lines)
2. FG BOM: raw/pack inputs NOT producible by WIP lines, directly consumed by X-lines
"""

from src.model.sku import SKU
from src.psp.types import LineAssignment, MaterialOrder
from src.psp.planner_wip import build_wip_producible_set


def run(
    fg_plan: list[LineAssignment],
    wip_plan: list[LineAssignment],
    topology_nodes: dict,
    sku_registry: dict[str, SKU],
    all_fg_skus: set[str],
) -> list[MaterialOrder]:
    wip_producible = build_wip_producible_set(topology_nodes)
    material_orders: list[MaterialOrder] = []

    for wip_entry in wip_plan:
        wip_sku = wip_entry.sku
        wip_qty = wip_entry.quantity

        for name, cfg in topology_nodes.items():
            if cfg.get("type") != "production":
                continue
            lid = name.replace("workstation_", "")
            if lid != wip_entry.line_id:
                continue
            bom_entry = cfg["bom"].get(wip_sku)
            if bom_entry is None:
                continue
            for input_sku, input_qty in bom_entry["inputs"].items():
                total_input = wip_qty * input_qty
                target = "veg_raw_storage" if lid.startswith(("C", "DC", "XC")) else "raw_material_storage"
                material_orders.append(MaterialOrder(
                    shift_index=wip_entry.shift_index,
                    sku=input_sku,
                    quantity=total_input,
                    target_warehouse=target,
                ))
            break

    for fg_entry in fg_plan:
        if not fg_entry.feasible:
            continue
        fg_sku = fg_entry.sku
        fg_qty = fg_entry.quantity

        for name, cfg in topology_nodes.items():
            if cfg.get("type") != "production":
                continue
            lid = name.replace("workstation_", "")
            if lid != fg_entry.line_id:
                continue
            bom_entry = cfg["bom"].get(fg_sku)
            if bom_entry is None:
                continue
            for input_sku, input_qty in bom_entry["inputs"].items():
                if input_sku in all_fg_skus or input_sku in wip_producible:
                    continue
                total_input = fg_qty * input_qty
                material_orders.append(MaterialOrder(
                    shift_index=fg_entry.shift_index,
                    sku=input_sku,
                    quantity=total_input,
                    target_warehouse="raw_material_storage",
                ))
            break

    return material_orders
