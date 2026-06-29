"""Orchestrate the two-sweep PSP planning pipeline."""

from collections import defaultdict
from pathlib import Path

from src.model.sku import SKU
from src.psp import loader
from src.psp.shift_calendar import build_shifts
from src.psp.planner_fg import run as run_fg, group_capacity
from src.psp.planner_wip import run as run_wip
from src.psp.planner_material import run as run_material
from src.psp.types import PspPlan


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
) -> list[dict]:
    report: list[dict] = []

    for day in range(1, num_days + 1):
        day_shifts = [s for s in shifts if s.day == day]
        day_fg = sum(a.quantity for a in fg_plan if a.shift_index in {s.index for s in day_shifts})
        day_wip = sum(a.quantity for a in wip_plan if a.shift_index in {s.index for s in day_shifts})
        day_wip_needed = sum(
            sum(q for q in need.values())
            for si, need in wip_need_by_shift.items()
            if si in {s.index for s in day_shifts}
        )

        report.append({
            "day": day,
            "demand_qty": daily_demand.get(day, 0),
            "fg_produced": day_fg,
            "fg_delivered": daily_delivered.get(day, 0),
            "fg_shortage": daily_shortage.get(day, 0),
            "wip_needed": round(day_wip_needed),
            "wip_produced": day_wip,
        })

    return report


def run_plan(scenario_path: Path, num_days: int) -> PspPlan:
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
    )
    total_fg = sum(a.quantity for a in fg_plan)
    print(f"[PSP] FG plan: {len(fg_plan)} assignments, {total_fg} total units")

    print("[PSP] === Sweep 2: WIP Planning ===")
    wip_plan, wip_need_by_shift = run_wip(
        shifts, fg_plan, topology_nodes, sku_registry,
        init_stock, all_fg_skus,
    )
    total_wip = sum(a.quantity for a in wip_plan)
    print(f"[PSP] WIP plan: {len(wip_plan)} assignments, {total_wip} total units")

    print("[PSP] === Material Procurement ===")
    material_orders = run_material(fg_plan, wip_plan, topology_nodes, sku_registry, all_fg_skus)
    print(f"[PSP] Material orders: {len(material_orders)}")

    init_fg = dict(init_stock.get("fg_storage", {}))
    for sku in all_fg_skus:
        init_fg.setdefault(sku, 0)
    total_init_fg = sum(init_fg.values())

    daily_report = build_daily_report(
        num_days, shifts, fg_plan, wip_plan,
        daily_demand, daily_delivered, daily_shortage,
        wip_need_by_shift, init_fg, all_fg_skus,
    )

    return PspPlan(
        shifts=shifts,
        fg_assignments=fg_plan,
        wip_assignments=wip_plan,
        material_orders=material_orders,
        shortages=shortages,
        shipment_delivered=shipment_delivered,
        daily_report=daily_report,
        init_fg_stock=total_init_fg,
    )
