"""Derive per-shift material movements from FG/WIP plans and material orders."""

from collections import defaultdict

from src.model.sku import SKU
from src.psp.types import LineAssignment, MaterialMovement, MaterialOrder
from src.psp.planner_wip import build_wip_producible_set


def build_line_prep_map(topology_nodes: dict) -> dict[str, str]:
    prep_map: dict[str, str] = {}
    for name, cfg in topology_nodes.items():
        if cfg.get("type") != "production":
            continue
        lid = name.replace("workstation_", "")
        if not lid.startswith("X") or lid.startswith("XC"):
            continue
        upstream = cfg.get("upstream", "")
        if "prep_storage_1" in upstream:
            prep_map[lid] = "prep_storage_1"
        elif "prep_storage_2" in upstream:
            prep_map[lid] = "prep_storage_2"
    return prep_map


def build_line_type_map(topology_nodes: dict) -> dict[str, str]:
    type_map: dict[str, str] = {}
    for name, cfg in topology_nodes.items():
        if cfg.get("type") != "production":
            continue
        lid = name.replace("workstation_", "")
        upstream = cfg.get("upstream", "")
        if "lineside_J" in upstream or "lineside_ZJ" in upstream:
            type_map[lid] = "J"
        elif "lineside_F" in upstream or "lineside_DF" in upstream or "lineside_FB" in upstream or "lineside_H" in upstream or "lineside_ZL" in upstream:
            type_map[lid] = "F"
        elif "lineside_C" in upstream or "lineside_DC" in upstream:
            type_map[lid] = "C"
        elif "lineside_XC" in upstream:
            type_map[lid] = "XC"
        elif "lineside_X" in upstream:
            type_map[lid] = "X"
    return type_map


def get_bom_inputs(topology_nodes: dict, line_id: str, sku: str) -> dict[str, float]:
    for name, cfg in topology_nodes.items():
        if cfg.get("type") != "production":
            continue
        lid = name.replace("workstation_", "")
        if lid != line_id:
            continue
        bom_entry = cfg["bom"].get(sku)
        if bom_entry is None:
            return {}
        return dict(bom_entry["inputs"])
    return {}


def derive_movements(
    fg_plan: list[LineAssignment],
    wip_plan: list[LineAssignment],
    material_orders: list[MaterialOrder],
    topology_nodes: dict,
    sku_registry: dict[str, SKU],
    all_fg_skus: set[str],
    shipment_delivered: dict[str, int],
    shifts: list,
    demand_orders: list[dict] | None = None,
    shortages: dict[str, int] | None = None,
) -> list[MaterialMovement]:
    movements: list[MaterialMovement] = []
    wip_producible = build_wip_producible_set(topology_nodes)
    line_prep_map = build_line_prep_map(topology_nodes)
    line_type_map = build_line_type_map(topology_nodes)

    num_shifts = len(shifts)

    # Index FG plan by shift for quick lookup
    fg_by_shift: dict[int, list[LineAssignment]] = defaultdict(list)
    for a in fg_plan:
        fg_by_shift[a.shift_index].append(a)

    # Index WIP plan by shift
    wip_by_shift: dict[int, list[LineAssignment]] = defaultdict(list)
    for a in wip_plan:
        wip_by_shift[a.shift_index].append(a)

    # ================================================================
    # 1) Purchase receipts: source → warehouse
    #    order/movement happen in same shift
    # ================================================================
    for mo in material_orders:
        movements.append(MaterialMovement(
            shift_index=mo.shift_index,
            from_node="source",
            to_node=mo.target_warehouse,
            sku=mo.sku,
            quantity=mo.quantity,
            movement_type="purchase_receipt",
        ))

    # ================================================================
    # 2) Material to lineside for WIP production (shift T-1)
    #    + WIP output (shift T)
    #    + WIP to prep_storage (shift T+1)
    # ================================================================
    for wip_entry in wip_plan:
        shift_t = wip_entry.shift_index
        line_id = wip_entry.line_id
        sku = wip_entry.sku
        qty = wip_entry.quantity

        line_type = line_type_map.get(line_id, "")
        is_veg = line_type in ("C", "XC")
        raw_wh = "veg_raw_storage" if is_veg else "raw_material_storage"
        wip_wh = "veg_wip_storage" if is_veg else "wip_storage"

        # BOM inputs for this WIP production
        bom_inputs = get_bom_inputs(topology_nodes, line_id, sku)

        # 2a) Material to lineside at shift T-1
        mat_shift = shift_t - 1
        if mat_shift >= 0:
            for input_sku, input_qty in bom_inputs.items():
                total_input = qty * input_qty
                movements.append(MaterialMovement(
                    shift_index=mat_shift,
                    from_node=raw_wh,
                    to_node=f"lineside_{line_id}",
                    sku=input_sku,
                    quantity=total_input,
                    movement_type="material_to_lineside",
                ))

        # 2b) WIP output at shift T
        movements.append(MaterialMovement(
            shift_index=shift_t,
            from_node=f"output_{line_id}",
            to_node=wip_wh,
            sku=sku,
            quantity=float(qty),
            movement_type="wip_output",
        ))

        # 2c) WIP to prep_storage at shift T+1
        wip_move_shift = shift_t + 1
        if wip_move_shift < num_shifts:
            fg_need = _compute_wip_prep_split(
                sku, float(qty), fg_by_shift.get(wip_move_shift + 1, []),
                topology_nodes, wip_producible, line_prep_map,
            )
            for prep_wh, prep_qty in fg_need.items():
                if prep_qty > 0:
                    movements.append(MaterialMovement(
                        shift_index=wip_move_shift,
                        from_node=wip_wh,
                        to_node=prep_wh,
                        sku=sku,
                        quantity=prep_qty,
                        movement_type="wip_to_prep",
                    ))

    # ================================================================
    # 3) FG-related movements
    #    - WIP/direct material to lineside (shift T-1)
    #    - FG output (shift T)
    # ================================================================
    for fg_entry in fg_plan:
        if not fg_entry.feasible:
            continue
        shift_t = fg_entry.shift_index
        line_id = fg_entry.line_id
        fg_sku = fg_entry.sku
        fg_qty = fg_entry.quantity

        prep_wh = line_prep_map.get(line_id, "prep_storage_1")

        # 3a) WIP/direct material to lineside at shift T-1
        mat_shift = shift_t - 1
        if mat_shift >= 0:
            bom_inputs = get_bom_inputs(topology_nodes, line_id, fg_sku)
            for input_sku, input_qty in bom_inputs.items():
                total_input = fg_qty * input_qty
                mt = "wip_to_lineside" if input_sku in wip_producible else "direct_to_lineside"
                from_wh = prep_wh if input_sku in wip_producible else "raw_material_storage"
                movements.append(MaterialMovement(
                    shift_index=mat_shift,
                    from_node=from_wh,
                    to_node=f"lineside_{line_id}",
                    sku=input_sku,
                    quantity=total_input,
                    movement_type=mt,
                ))

        # 3b) FG output at shift T
        movements.append(MaterialMovement(
            shift_index=shift_t,
            from_node=f"output_{line_id}",
            to_node="fg_storage",
            sku=fg_sku,
            quantity=float(fg_qty),
            movement_type="fg_output",
        ))

    # ================================================================
    # 4) FG shipment: fg_storage → sink
    #    at the day-shift matching each demand order's start_time
    # ================================================================
    shift_by_start: dict[int, int] = {}
    for s in shifts:
        if s.type == "day":
            shift_by_start[s.start_time] = s.index

    if demand_orders and shortages is not None:
        total_demand_per_sku: dict[str, int] = defaultdict(int)
        for d in demand_orders:
            if d["sku"] in all_fg_skus:
                total_demand_per_sku[d["sku"]] += d["quantity"]
        for d in demand_orders:
            sku = d["sku"]
            if sku not in all_fg_skus or d["quantity"] <= 0:
                continue
            t = int(d["start_time"])
            shift_idx = shift_by_start.get(t)
            if shift_idx is None:
                continue
            total_dmd = total_demand_per_sku.get(sku, 1)
            delivered = shipment_delivered.get(sku, 0)
            ship_qty = d["quantity"] * delivered / max(total_dmd, 1)
            if ship_qty > 0.001:
                movements.append(MaterialMovement(
                    shift_index=shift_idx,
                    from_node="fg_storage",
                    to_node="sink",
                    sku=sku,
                    quantity=ship_qty,
                    movement_type="fg_shipment",
                ))
    elif shipment_delivered:
        for s in shifts:
            if s.type == "day":
                for sku, qty in shipment_delivered.items():
                    if qty > 0:
                        movements.append(MaterialMovement(
                            shift_index=s.index,
                            from_node="fg_storage",
                            to_node="sink",
                            sku=sku,
                            quantity=float(qty),
                            movement_type="fg_shipment",
                        ))
                break

    movements.sort(key=lambda m: (m.shift_index, m.movement_type, m.from_node, m.to_node, m.sku))
    return movements


def _compute_wip_prep_split(
    wip_sku: str,
    wip_qty: float,
    fg_assignments_at_t2: list[LineAssignment],
    topology_nodes: dict,
    wip_producible: set[str],
    line_prep_map: dict[str, str],
) -> dict[str, float]:
    if not fg_assignments_at_t2:
        return {"prep_storage_1": wip_qty}

    total_fg_need: dict[str, float] = defaultdict(float)
    for fg_entry in fg_assignments_at_t2:
        if not fg_entry.feasible:
            continue
        prep_wh = line_prep_map.get(fg_entry.line_id, "prep_storage_1")
        bom_inputs = get_bom_inputs(topology_nodes, fg_entry.line_id, fg_entry.sku)
        for input_sku, input_qty in bom_inputs.items():
            if input_sku == wip_sku:
                total_fg_need[prep_wh] += fg_entry.quantity * input_qty

    total_needed = sum(total_fg_need.values())
    if total_needed <= 0:
        return {"prep_storage_1": wip_qty}

    result: dict[str, float] = {}
    remaining = wip_qty
    for prep_wh, need in total_fg_need.items():
        alloc = min(need / total_needed * wip_qty, remaining)
        result[prep_wh] = round(alloc, 4)
        remaining -= alloc
    if remaining > 0.001:
        result["prep_storage_1"] = result.get("prep_storage_1", 0) + remaining

    return result