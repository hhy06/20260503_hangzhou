"""Sweep 2: WIP production planning — derive from FG plan via BOM."""

from bisect import bisect_left
from collections import defaultdict

from src.model.sku import SKU
from src.psp.planner_selection import pick_sku
from src.psp.types import Shift, LineAssignment


SHIFT_DURATION = 690
LOOKAHEAD_SHIFTS = 6


def get_speed(line_bom_entry: dict, sku_registry: dict[str, SKU], sku: str) -> float:
    speed = line_bom_entry.get("speed", 0)
    if speed and speed > 0:
        return speed
    sku_obj = sku_registry.get(sku)
    if sku_obj and sku_obj.bom_speed > 0:
        return sku_obj.bom_speed
    raise ValueError(
        f"SKU {sku} has no valid speed — "
        f"topology speed={speed}, "
        f"bom_speed={sku_obj.bom_speed if sku_obj else 'SKU_NOT_IN_REGISTRY'}"
    )


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
    decision_mode: int = 1,
) -> tuple[list[LineAssignment], dict[int, dict[str, float]]]:
    wip_lines, line_skus, capacity = build_wip_lines(topology_nodes, sku_registry)
    wip_producible = build_wip_producible_set(topology_nodes)
    wip_need_by_shift = compute_wip_need(fg_plan, topology_nodes, wip_producible)

    init_wip: dict[str, float] = defaultdict(float)
    for wh in ["prep_storage_1", "prep_storage_2", "wip_storage", "veg_wip_storage"]:
        for sku, qty in init_stock.get(wh, {}).items():
            init_wip[sku] += qty

    wip_plan: list[LineAssignment] = []

    # --- Build WIP demand analogues (mirroring FG's demand_by_time) ---
    wip_need_times = sorted(wip_need_by_shift.keys())

    wip_need_days: list[int] = []
    shift_index_to_day: dict[int, int] = {s.index: s.day for s in shifts}
    for si in wip_need_times:
        wip_need_days.append(shift_index_to_day.get(si, 1))

    cum_wip_need: dict[str, list[float]] = {}
    all_wip_skus: set[str] = set()
    for skus in wip_need_by_shift.values():
        all_wip_skus.update(skus.keys())
    for skus in line_skus.values():
        all_wip_skus.update(skus)
    for sku in sorted(all_wip_skus):
        running = 0.0
        series: list[float] = []
        for si in wip_need_times:
            running += wip_need_by_shift[si].get(sku, 0.0)
            series.append(running)
        cum_wip_need[sku] = series

    # --- Initialize WIP stock and produced-so-far ---
    wip_stock: dict[str, float] = defaultdict(float)
    wip_produced: dict[str, float] = defaultdict(float)
    for sku, qty in init_wip.items():
        wip_stock[sku] = qty
        wip_produced[sku] = qty

    # --- Window/rolling pointers for WIP need ---
    window_wip_need: dict[str, float] = defaultdict(float)
    window_ptr: int = 0

    roll_wip_need: dict[str, float] = defaultdict(float)
    roll_ptr_add: int = 0
    roll_ptr_rem: int = 0

    for shift in shifts:
        si = shift.index

        # Advance window: include WIP need from si to si + LOOKAHEAD_SHIFTS
        while (window_ptr < len(wip_need_times)
               and wip_need_times[window_ptr] <= si + LOOKAHEAD_SHIFTS):
            t = wip_need_times[window_ptr]
            for sku, qty in wip_need_by_shift[t].items():
                window_wip_need[sku] += qty
            window_ptr += 1

        # Advance rolling window: remove WIP need before si
        while (roll_ptr_rem < len(wip_need_times)
               and wip_need_times[roll_ptr_rem] < si):
            t = wip_need_times[roll_ptr_rem]
            for sku, qty in wip_need_by_shift[t].items():
                roll_wip_need[sku] -= qty
            roll_ptr_rem += 1
        # Add WIP need up to si + LOOKAHEAD_SHIFTS
        while (roll_ptr_add < len(wip_need_times)
               and wip_need_times[roll_ptr_add] <= si + LOOKAHEAD_SHIFTS):
            t = wip_need_times[roll_ptr_add]
            for sku, qty in wip_need_by_shift[t].items():
                roll_wip_need[sku] += qty
            roll_ptr_add += 1

        # Consume WIP stock by this shift's WIP need (analogous to FG demand fulfillment)
        need_this_shift = wip_need_by_shift.get(si, {})
        for sku, qty in need_this_shift.items():
            wip_stock[sku] -= qty

        lines_this_shift = list(wip_lines)
        lines_this_shift.sort()

        for lid in lines_this_shift:
            eligible = line_skus.get(lid, [])
            if not eligible:
                continue

            best_sku = pick_sku(
                eligible, decision_mode,
                stock=wip_stock,
                window_demand=window_wip_need,
                roll_demand=roll_wip_need,
                produced_so_far=wip_produced,
                cum_demand_series=cum_wip_need,
                shipment_days=wip_need_days,
            )
            if best_sku is None:
                best_sku = eligible[0]

            cap = capacity[lid]
            qty = cap.get(best_sku, 0)
            if qty <= 0:
                qty = 1

            wip_plan.append(LineAssignment(
                shift_index=shift.index,
                line_id=lid,
                sku=best_sku,
                quantity=qty,
                feasible=True,
            ))

            wip_stock[best_sku] += qty
            wip_produced[best_sku] += qty

    return wip_plan, wip_need_by_shift
