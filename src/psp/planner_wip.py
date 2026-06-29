"""Sweep 2: WIP production planning — derive from FG plan via BOM."""

from collections import defaultdict

from src.model.sku import SKU
from src.psp.types import Shift, LineAssignment


SHIFT_DURATION = 690


def get_speed(line_bom_entry: dict, sku_registry: dict[str, SKU], sku: str) -> float:
    speed = line_bom_entry.get("speed", 0)
    if speed and speed > 0:
        return speed
    sku_obj = sku_registry.get(sku)
    if sku_obj and sku_obj.bom_speed > 0:
        return sku_obj.bom_speed
    return 1.0


def build_wip_lines(
    topology_nodes: dict, sku_registry: dict[str, SKU],
) -> tuple[list[str], dict[str, list[str]], dict[str, dict[str, int]]]:
    wip_lines: list[str] = []
    line_skus: dict[str, list[str]] = {}
    capacity: dict[str, dict[str, int]] = {}

    for name, cfg in topology_nodes.items():
        if cfg.get("type") != "production":
            continue
        lid = name.replace("workstation_", "")
        if lid.startswith("X") and not lid.startswith("XC"):
            continue
        wip_lines.append(lid)
        eligible = [sku for sku in cfg["bom"]]
        eligible.sort()
        line_skus[lid] = eligible
        cap = {}
        for sku in eligible:
            entry = cfg["bom"][sku]
            spd = get_speed(entry, sku_registry, sku)
            cap[sku] = max(1, int(spd * SHIFT_DURATION))
        capacity[lid] = cap

    return wip_lines, line_skus, capacity


def build_wip_producible_set(topology_nodes: dict) -> set[str]:
    producible: set[str] = set()
    for name, cfg in topology_nodes.items():
        if cfg.get("type") != "production":
            continue
        lid = name.replace("workstation_", "")
        if lid.startswith("X") and not lid.startswith("XC"):
            continue
        for sku in cfg["bom"]:
            producible.add(sku)
    return producible


def compute_wip_need(
    fg_plan: list[LineAssignment],
    topology_nodes: dict,
    wip_producible: set[str],
) -> dict[int, dict[str, float]]:
    wip_need: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for entry in fg_plan:
        if not entry.feasible:
            continue
        fg_sku = entry.sku
        fg_qty = entry.quantity
        fg_shift = entry.shift_index

        for name, cfg in topology_nodes.items():
            if cfg.get("type") != "production":
                continue
            lid = name.replace("workstation_", "")
            if lid != entry.line_id:
                continue
            bom_entry = cfg["bom"].get(fg_sku)
            if bom_entry is None:
                continue
            for input_sku, input_qty in bom_entry["inputs"].items():
                if input_sku not in wip_producible:
                    continue
                total_input = fg_qty * input_qty
                needed_by_shift = fg_shift - 2
                if needed_by_shift < 0:
                    continue
                wip_need[needed_by_shift][input_sku] += total_input
            break

    return dict(wip_need)


def run(
    shifts: list[Shift],
    fg_plan: list[LineAssignment],
    topology_nodes: dict,
    sku_registry: dict[str, SKU],
    init_stock: dict[str, dict[str, int]],
    all_fg_skus: set[str],
) -> tuple[list[LineAssignment], dict[int, dict[str, float]]]:
    wip_lines, line_skus, capacity = build_wip_lines(topology_nodes, sku_registry)
    wip_producible = build_wip_producible_set(topology_nodes)

    wip_need_by_shift = compute_wip_need(fg_plan, topology_nodes, wip_producible)

    init_wip: dict[str, float] = defaultdict(float)
    for wh in ["prep_storage_1", "prep_storage_2", "wip_storage", "veg_wip_storage"]:
        for sku, qty in init_stock.get(wh, {}).items():
            init_wip[sku] += qty

    remaining: dict[str, float] = defaultdict(float)
    for sku, qty in init_wip.items():
        remaining[sku] = qty

    wip_plan: list[LineAssignment] = []

    line_rr_pos: dict[str, int] = {}

    for shift in shifts:
        need_this_shift = wip_need_by_shift.get(shift.index, {})
        for sku, qty in need_this_shift.items():
            remaining[sku] += qty

        lines_this_shift = list(wip_lines)
        lines_this_shift.sort()

        for lid in lines_this_shift:
            eligible = line_skus.get(lid, [])
            if not eligible:
                continue
            cap = capacity[lid]

            best_sku = None
            best_need = -1.0
            pos = line_rr_pos.get(lid, 0)
            for i in range(len(eligible)):
                sku = eligible[(pos + i) % len(eligible)]
                need = remaining.get(sku, 0.0)
                if need > best_need:
                    best_need = need
                    best_sku = sku
            line_rr_pos[lid] = (pos + 1) % len(eligible) if best_sku else 0

            sku = best_sku or eligible[0]
            qty = cap.get(sku, 0)
            if qty <= 0:
                qty = 1

            wip_plan.append(LineAssignment(
                shift_index=shift.index,
                line_id=lid,
                sku=sku,
                quantity=qty,
                feasible=True,
            ))

            remaining[sku] = max(0.0, remaining[sku] - qty)

    return wip_plan, wip_need_by_shift
