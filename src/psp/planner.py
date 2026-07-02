"""Orchestrate the two-sweep PSP planning pipeline."""

import math
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from src.model.sku import SKU
from src.psp import loader
from src.psp.shift_calendar import build_shifts
from src.psp.planner_fg import run as run_fg, group_capacity
from src.psp.planner_wip import run as run_wip
from src.psp.planner_material import run as run_material
from src.psp.planner_movement import derive_movements
from src.psp.types import PspPlan


CONSUMPTION_MOVEMENTS = {"material_to_lineside", "wip_to_lineside", "direct_to_lineside"}


def _collect_storage_nodes(topology_nodes: dict) -> list[str]:
    nodes: list[str] = []
    for name, cfg in topology_nodes.items():
        if cfg.get("type") in ("warehouse",):
            nodes.append(name)
    return sorted(nodes)


def _to_pallets(qty: float, sku: str, sku_registry: dict[str, SKU]) -> int:
    sku_obj = sku_registry.get(sku)
    if sku_obj is None or sku_obj.pallet_size is None or sku_obj.pallet_size <= 0:
        return int(math.ceil(qty)) if qty > 0 else 0
    return int(math.ceil(qty / sku_obj.pallet_size))


def _compute_pallet_stats_and_inventory(
    num_days: int,
    num_shifts: int,
    movements: list,
    sku_registry: dict[str, SKU],
    init_stock: dict[str, dict[str, int]],
    storage_nodes: list[str],
) -> tuple[list[dict], list[dict]]:
    lineside_nodes = {n for n in storage_nodes if n.startswith("lineside_")}
    output_nodes = {n for n in storage_nodes if n.startswith("output_")}
    pass_through = lineside_nodes | output_nodes

    movements_by_shift: dict[int, list] = defaultdict(list)
    for m in movements:
        movements_by_shift[m.shift_index].append(m)

    inventory: dict[str, dict[str, float]] = {}
    for node in storage_nodes:
        inv: dict[str, float] = defaultdict(float)
        for sku, qty in init_stock.get(node, {}).items():
            inv[sku] = float(qty)
        inventory[node] = inv

    daily_stats: list[dict] = []
    daily_inventory: list[dict] = []

    for day in range(1, num_days + 1):
        day_shift_idx = 2 * (day - 1)
        night_shift_idx = 2 * day - 1
        day_shift_indices = {day_shift_idx, night_shift_idx}

        source_out_pallets = 0
        consumed_pallets = 0
        shortage_nodes: set[str] = set()

        for shift_idx in range(day_shift_idx + 1):
            for m in movements_by_shift.get(shift_idx, []):
                to_node = m.to_node
                from_node = m.from_node
                sku = m.sku
                qty = m.quantity

                if to_node in storage_nodes and to_node not in pass_through:
                    inventory[to_node][sku] += qty
                if from_node in storage_nodes and from_node not in pass_through:
                    inventory[from_node][sku] -= qty
                    if inventory[from_node][sku] < -0.001:
                        shortage_nodes.add(from_node)

                if shift_idx in day_shift_indices:
                    if m.movement_type == "purchase_receipt":
                        source_out_pallets += _to_pallets(qty, sku, sku_registry)
                    if m.movement_type in CONSUMPTION_MOVEMENTS:
                        consumed_pallets += _to_pallets(qty, sku, sku_registry)

        for node in pass_through:
            inventory[node].clear()

        inv_snapshot: dict[str, int] = {}
        for node in storage_nodes:
            if node in pass_through:
                inv_snapshot[node] = 0
            else:
                total = 0
                for sku, qty in inventory[node].items():
                    if qty > 0.001:
                        total += _to_pallets(qty, sku, sku_registry)
                inv_snapshot[node] = total

        daily_stats.append({
            "day": day,
            "source_out_pallets": source_out_pallets,
            "consumed_pallets": consumed_pallets,
            "shortage_nodes": sorted(shortage_nodes),
        })
        daily_inventory.append(inv_snapshot)

    return daily_stats, daily_inventory


def build_daily_report(
    num_days: int,
    shifts: list,
    fg_plan: list,
    wip_plan: list,
    daily_demand: dict[int, int],
    daily_delivered: dict[int, int],
    daily_shortage: dict[int, int],
    wip_need_by_shift: dict[int, dict[str, float]],
    init_fg_stock: dict[str, int],
    all_fg_skus: set[str],
    wip_shortage_by_day: dict[int, float] | None = None,
    wip_day_end_stock: dict[int, float] | None = None,
    movements: list | None = None,
    sku_registry: dict[str, SKU] | None = None,
    init_stock: dict[str, dict[str, int]] | None = None,
    topology_nodes: dict | None = None,
) -> list[dict]:
    report: list[dict] = []

    pallet_stats = None
    inv_snapshots = None
    if movements and sku_registry and init_stock and topology_nodes:
        storage_nodes = _collect_storage_nodes(topology_nodes)
        pallet_stats, inv_snapshots = _compute_pallet_stats_and_inventory(
            num_days, len(shifts), movements, sku_registry, init_stock, storage_nodes,
        )

    for day in range(1, num_days + 1):
        day_shifts = [s for s in shifts if s.day == day]
        day_fg = sum(a.quantity for a in fg_plan if a.shift_index in {s.index for s in day_shifts})
        day_wip = sum(a.quantity for a in wip_plan if a.shift_index in {s.index for s in day_shifts})
        day_wip_needed = sum(
            sum(q for q in need.values())
            for si, need in wip_need_by_shift.items()
            if si in {s.index for s in day_shifts}
        )

        demand_qty = daily_demand.get(day, 0)
        short_qty = daily_shortage.get(day, 0)
        short_pct = round(100.0 * short_qty / demand_qty, 2) if demand_qty > 0 else 0.0

        wip_short = round(wip_shortage_by_day.get(day, 0.0)) if wip_shortage_by_day else None
        wip_short_pct = (
            round(100.0 * wip_short / day_wip_needed, 2)
            if wip_shortage_by_day and day_wip_needed > 0
            else None
        )
        wip_stock = round(wip_day_end_stock.get(day, 0.0)) if wip_day_end_stock else None

        entry = {
            "day": day,
            "demand_qty": demand_qty,
            "fg_produced": day_fg,
            "fg_delivered": daily_delivered.get(day, 0),
            "fg_shortage": short_qty,
            "fg_short_pct": short_pct,
            "wip_needed": round(day_wip_needed),
            "wip_produced": day_wip,
            "wip_shortage": wip_short,
            "wip_short_pct": wip_short_pct,
            "wip_stock_end": wip_stock,
        }

        if pallet_stats:
            entry["source_out_pallets"] = pallet_stats[day - 1]["source_out_pallets"]
            entry["consumed_pallets"] = pallet_stats[day - 1]["consumed_pallets"]
            entry["shortage_nodes"] = pallet_stats[day - 1]["shortage_nodes"]
            entry["inventory"] = inv_snapshots[day - 1] if inv_snapshots else {}

        report.append(entry)

    return report


def run_plan(scenario_path: Path, num_days: int, decision_mode: int = 1) -> PspPlan:
    print(f"[PSP] Loading scenario: {scenario_path.name}")
    sku_registry: dict[str, SKU] = loader.load_skus_and_bom(scenario_path)
    demand_orders = loader.load_demand(scenario_path)
    init_stock = loader.load_init_stock(scenario_path)
    topology_nodes, topology_edges = loader.load_topology(
        scenario_path.parent.parent, scenario_path.name,
    )

    shifts = build_shifts(num_days)
    print(f"[PSP] {len(shifts)} shifts over {num_days} days")

    x_lines, line_skus, fg_capacity, all_fg_skus = group_capacity(topology_nodes, sku_registry)
    print(f"[PSP] {len(x_lines)} X-lines, {len(all_fg_skus)} FG SKUs")

    print("[PSP] === Sweep 1: FG Planning ===")
    fg_plan, shortages, shipment_delivered, daily_demand, daily_delivered, daily_shortage = run_fg(
        shifts, topology_nodes, sku_registry, init_stock,
        demand_orders, x_lines, line_skus, fg_capacity, all_fg_skus,
        decision_mode=decision_mode,
    )
    total_fg = sum(a.quantity for a in fg_plan)
    print(f"[PSP] FG plan: {len(fg_plan)} assignments, {total_fg} total units")

    print("[PSP] === Sweep 2: WIP Planning ===")
    wip_plan, wip_need_by_shift, wip_shortage_by_day, wip_day_end_stock = run_wip(
        shifts, fg_plan, topology_nodes, sku_registry,
        init_stock, all_fg_skus,
        decision_mode=decision_mode,
    )
    total_wip = sum(a.quantity for a in wip_plan)
    print(f"[PSP] WIP plan: {len(wip_plan)} assignments, {total_wip} total units")

    print("[PSP] === Material Procurement ===")
    material_orders = run_material(fg_plan, wip_plan, topology_nodes, sku_registry, all_fg_skus)
    print(f"[PSP] Material orders: {len(material_orders)}")

    print("[PSP] === Deriving Material Movements ===")
    movements = derive_movements(
        fg_plan, wip_plan, material_orders, topology_nodes,
        sku_registry, all_fg_skus, shipment_delivered, shifts,
        demand_orders=demand_orders, shortages=shortages,
    )
    print(f"[PSP] Material movements: {len(movements)}")

    init_fg = dict(init_stock.get("fg_storage", {}))
    for sku in all_fg_skus:
        init_fg.setdefault(sku, 0)
    total_init_fg = sum(init_fg.values())

    daily_report = build_daily_report(
        num_days, shifts, fg_plan, wip_plan,
        daily_demand, daily_delivered, daily_shortage,
        wip_need_by_shift, init_fg, all_fg_skus,
        wip_shortage_by_day=wip_shortage_by_day,
        wip_day_end_stock=wip_day_end_stock,
        movements=movements, sku_registry=sku_registry,
        init_stock=init_stock, topology_nodes=topology_nodes,
    )

    return PspPlan(
        shifts=shifts,
        fg_assignments=fg_plan,
        wip_assignments=wip_plan,
        material_orders=material_orders,
        movements=movements,
        shortages=shortages,
        shipment_delivered=shipment_delivered,
        daily_report=daily_report,
        init_fg_stock=total_init_fg,
    )
