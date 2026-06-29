"""Sweep 1: FG production planning — optimistic, pure demand-driven."""

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
    raise ValueError(
        f"SKU {sku} has no valid speed — "
        f"topology speed={speed}, "
        f"bom_speed={sku_obj.bom_speed if sku_obj else 'SKU_NOT_IN_REGISTRY'}"
    )


def group_capacity(
    topology_nodes: dict, sku_registry: dict[str, SKU],
) -> tuple[list[str], dict[str, list[str]], dict[str, dict[str, int]], set[str]]:
    x_lines: list[str] = []
    line_skus: dict[str, list[str]] = {}
    capacity: dict[str, dict[str, int]] = {}
    all_fg_skus: set[str] = set()

    for name, cfg in topology_nodes.items():
        if cfg.get("type") != "production":
            continue
        lid = name.replace("workstation_", "")
        if not lid.startswith("X") or lid.startswith("XC"):
            continue
        x_lines.append(lid)
        eligible = []
        for sku, entry in cfg["bom"].items():
            eligible.append(sku)
            all_fg_skus.add(sku)
        eligible.sort()
        line_skus[lid] = eligible
        cap = {}
        for sku in eligible:
            entry = cfg["bom"][sku]
            spd = get_speed(entry, sku_registry, sku)
            cap[sku] = max(1, int(spd * SHIFT_DURATION))
        capacity[lid] = cap

    return x_lines, line_skus, capacity, all_fg_skus


def run(
    shifts: list[Shift],
    topology_nodes: dict,
    sku_registry: dict[str, SKU],
    init_stock: dict[str, dict[str, int]],
    demand_orders: list[dict],
    x_lines: list[str],
    line_skus: dict[str, list[str]],
    capacity: dict[str, dict[str, int]],
    all_fg_skus: set[str],
) -> tuple[list[LineAssignment], dict[str, int], dict[str, int],
           dict[int, int], dict[int, int], dict[int, int]]:
    fg_stock: dict[str, int] = dict(init_stock.get("fg_storage", {}))
    for sku in all_fg_skus:
        fg_stock.setdefault(sku, 0)

    demand_by_time: dict[int, dict[str, int]] = {}
    for d in demand_orders:
        t = int(d["start_time"])
        sku = d["sku"]
        qty = d["quantity"]
        if qty > 0 and sku in all_fg_skus:
            demand_by_time.setdefault(t, {})[sku] = demand_by_time.get(t, {}).get(sku, 0) + qty

    shipment_times = sorted(demand_by_time.keys())
    shipment_ptr = 0

    shortages: dict[str, int] = defaultdict(int)
    shipment_delivered: dict[str, int] = defaultdict(int)

    daily_demand: dict[int, int] = {}
    daily_delivered: dict[int, int] = {}
    daily_shortage: dict[int, int] = {}

    produced_so_far: dict[str, int] = {}
    for sku in all_fg_skus:
        produced_so_far[sku] = init_stock.get("fg_storage", {}).get(sku, 0)

    window_demand: dict[str, int] = defaultdict(int)
    window_ptr: int = 0

    line_rr_pos: dict[str, int] = {}
    fg_plan: list[LineAssignment] = []

    for shift in shifts:
        next_idx = shift.index + 1
        if next_idx < len(shifts):
            cutoff = shifts[next_idx].end_time
        else:
            cutoff = shifts[-1].end_time
        while (window_ptr < len(shipment_times)
               and shipment_times[window_ptr] <= cutoff):
            t = shipment_times[window_ptr]
            for sku, qty in demand_by_time[t].items():
                window_demand[sku] += qty
            window_ptr += 1

        if shift.type == "day":
            ship_time = shift.start_time
            while shipment_ptr < len(shipment_times) and shipment_times[shipment_ptr] == ship_time:
                st = shipment_times[shipment_ptr]
                day = int((int(st) - 480) // 1440) + 1
                day_demand = 0
                day_deliver = 0
                day_short = 0
                for sku, qty in demand_by_time.get(st, {}).items():
                    day_demand += qty
                    fulfill = min(fg_stock[sku], qty)
                    fg_stock[sku] -= fulfill
                    shipment_delivered[sku] += fulfill
                    day_deliver += fulfill
                    if fulfill < qty:
                        short = qty - fulfill
                        shortages[sku] += short
                        day_short += short
                daily_demand[day] = day_demand
                daily_delivered[day] = day_deliver
                daily_shortage[day] = day_short
                shipment_ptr += 1

        lines_in_shift = list(x_lines)
        lines_in_shift.sort()

        for lid in lines_in_shift:
            eligible = line_skus.get(lid, [])
            if not eligible:
                continue
            cap = capacity[lid]
            best_sku = None
            best_need = -1

            for sku in eligible:
                need = window_demand.get(sku, 0) - produced_so_far.get(sku, 0)
                if need > best_need:
                    best_need = need
                    best_sku = sku

            if best_sku is None or best_need <= 0:
                pos = line_rr_pos.get(lid, 0)
                best_sku = eligible[pos % len(eligible)]
                line_rr_pos[lid] = (pos + 1) % len(eligible)

            qty = cap.get(best_sku, 0)
            if qty <= 0:
                continue

            fg_plan.append(LineAssignment(
                shift_index=shift.index,
                line_id=lid,
                sku=best_sku,
                quantity=qty,
                feasible=True,
            ))

            fg_stock[best_sku] += qty
            produced_so_far[best_sku] += qty

    return fg_plan, shortages, shipment_delivered, daily_demand, daily_delivered, daily_shortage
