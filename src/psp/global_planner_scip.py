"""Global FG planning using SCIP MILP with rolling horizon."""
from datetime import datetime
from collections import defaultdict
from pyscipopt import Model, quicksum
from src.psp.types import Shift, LineAssignment


# === Configurable Parameters ===
WINDOW_DAYS = 30
FREEZE_DAYS = 10
SCIP_TIME_LIMIT = 50  ## per round 
SCIP_GAP = 0.10 
HOLDING_COST = 1e-4


def aggregate_demand_by_shift(
    demand_orders: list[dict],
    shifts: list[Shift],
    all_fg_skus: set[str],
) -> tuple[dict[int, dict[str, int]], dict[str, int]]:
    """Map continuous demand timestamps to discrete shift buckets.

    Demand at a day-shift start_time is routed to the *previous* shift
    (since fulfillment happens before production within a shift).
    Demand at the very first shift is returned separately for subtraction
    from initial stock.
    """
    demand_by_shift: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    first_shift_demand: dict[str, int] = defaultdict(int)

    for d in demand_orders:
        t_min = int(d["start_time"])
        sku = d["sku"]
        qty = d["quantity"]
        if qty <= 0 or sku not in all_fg_skus:
            continue

        assigned = None
        for s in shifts:
            if s.start_time <= t_min < s.end_time:
                if s.type == "day" and t_min == s.start_time:
                    if s.index > 0:
                        assigned = s.index - 1
                    else:
                        first_shift_demand[sku] += qty
                else:
                    assigned = s.index
                break

        if assigned is not None:
            demand_by_shift[assigned][sku] += qty

    return {k: dict(v) for k, v in demand_by_shift.items()}, dict(first_shift_demand)


def solve_window(
    shifts_window: list[Shift],
    init_stock: dict[str, int],
    demand_by_shift: dict[int, dict[str, int]],
    x_lines: list[str],
    line_skus: dict[str, list[str]],
    capacity: dict[str, dict[str, int]],
    all_fg_skus: set[str],
) -> tuple[list[LineAssignment], dict[int, dict[str, int]]]:
    """Build and solve a SCIP model for a subset of shifts.

    Returns (assignments, inventory_at_end_of_shift) where
    inventory_at_end_of_shift[t] = {sku: quantity}.
    """
    model = Model("PSP_FG_Window")
    model.hideOutput()

    shift_indices = [s.index for s in shifts_window]

    X: dict = {} # X[lid, sku, t] = 1 if sku is produced on line lid at time t
    I: dict = {} # I[sku, t] = inventory of sku at the end of shift t
    S: dict = {} # S[sku, t] = stockout of sku at the end of shift t

    for t in shift_indices:
        for sku in all_fg_skus:
            I[sku, t] = model.addVar(name=f"I_{sku}_{t}", vtype="CONTINUOUS", lb=0)
            S[sku, t] = model.addVar(name=f"S_{sku}_{t}", vtype="CONTINUOUS", lb=0)
        for lid in x_lines:
            for sku in line_skus.get(lid, []):
                X[lid, sku, t] = model.addVar(
                    name=f"X_{lid}_{sku}_{t}", vtype="BINARY"
                )

    for t in shift_indices:
        for lid in x_lines:
            eligible = line_skus.get(lid, [])
            if eligible:
                model.addCons(
                    quicksum(X[lid, sku, t] for sku in eligible) <= 1,
                    name=f"OneSku_{lid}_{t}",
                )

        for sku in all_fg_skus:
            prev_inv = (
                init_stock.get(sku, 0)
                if t == shift_indices[0]
                else I[sku, t - 1]
            )
            production = quicksum(
                capacity[lid][sku] * X[lid, sku, t]
                for lid in x_lines
                if sku in line_skus.get(lid, []) and sku in capacity[lid]
            )
            demand = demand_by_shift.get(t, {}).get(sku, 0)

            model.addCons(
                prev_inv + production - demand + S[sku, t] == I[sku, t],
                name=f"InvBal_{sku}_{t}",
            )

    obj = quicksum(
        S[sku, t] for sku in all_fg_skus for t in shift_indices
    ) + HOLDING_COST * quicksum(
        I[sku, t] for sku in all_fg_skus for t in shift_indices
    )
    model.setObjective(obj, "minimize")
    model.setParam("limits/gap", SCIP_GAP)
    model.setParam("limits/time", SCIP_TIME_LIMIT)
    model.optimize()

    status = model.getStatus()
    if status == "infeasible":
        raise RuntimeError(
            f"SCIP infeasible for window shifts {shift_indices[0]}-{shift_indices[-1]}"
        )

    assignments: list[LineAssignment] = []
    try:
        for t in shift_indices:
            for lid in x_lines:
                for sku in line_skus.get(lid, []):
                    if model.getVal(X[lid, sku, t]) > 0.5:
                        assignments.append(
                            LineAssignment(
                                shift_index=t,
                                line_id=lid,
                                sku=sku,
                                quantity=capacity[lid][sku],
                                feasible=True,
                            )
                        )
    except Exception:
        raise RuntimeError(
            f"SCIP returned status {status} with no feasible solution "
            f"for window shifts {shift_indices[0]}-{shift_indices[-1]}"
        )

    inventory_snapshots: dict[int, dict[str, int]] = {}
    for t in shift_indices:
        snap: dict[str, int] = {}
        for sku in all_fg_skus:
            snap[sku] = int(round(model.getVal(I[sku, t])))
        inventory_snapshots[t] = snap

    return assignments, inventory_snapshots


def run_rolling_global(
    shifts: list[Shift],
    init_stock: dict[str, dict[str, int]],
    demand_orders: list[dict],
    x_lines: list[str],
    line_skus: dict[str, list[str]],
    capacity: dict[str, dict[str, int]],
    all_fg_skus: set[str],
) -> list[LineAssignment]:
    """Rolling horizon: solve windows, freeze early shifts, advance."""
    demand_by_shift, first_shift_demand = aggregate_demand_by_shift(
        demand_orders, shifts, all_fg_skus
    )

    window_len = WINDOW_DAYS * 2
    freeze_len = FREEZE_DAYS * 2

    all_assignments: list[LineAssignment] = []

    # Initialise current inventory from init_stock, then
    # subtract first-shift demand (which must be fulfilled before any production).
    current_inv: dict[str, int] = dict(init_stock.get("fg_storage", {}))
    for sku in all_fg_skus:
        current_inv.setdefault(sku, 0)
    for sku, qty in first_shift_demand.items():
        current_inv[sku] = max(0, current_inv[sku] - qty)

    pos = 0
    
    while pos < len(shifts):

        current_time = datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time}] pos={pos} (total = {len(shifts)})")
        window_end = min(pos + window_len, len(shifts))
        window = shifts[pos:window_end]
        if not window:
            break

        assignments, inventory_snapshots = solve_window(
            window,
            current_inv,
            demand_by_shift,
            x_lines,
            line_skus,
            capacity,
            all_fg_skus,
        )

        freeze_end = min(pos + freeze_len, window_end)

        for a in assignments:
            if pos <= a.shift_index < freeze_end:
                all_assignments.append(a)

        # Carry forward inventory from the last frozen shift
        if freeze_end > pos:
            last_frozen_shift = shifts[freeze_end - 1]
            current_inv = dict(inventory_snapshots[last_frozen_shift.index])

        pos = freeze_end

    return all_assignments


def simulate_fulfillment(
    shifts: list[Shift],
    demand_orders: list[dict],
    fg_plan: list[LineAssignment],
    init_stock: dict[str, dict[str, int]],
    all_fg_skus: set[str],
) -> tuple[
    dict[str, int],
    dict[str, int],
    dict[int, int],
    dict[int, int],
    dict[int, int],
]:
    """Replay the same demand-fulfilment logic used by the heuristic modes.

    Mirrors the chronological loop in planner_fg.py lines 145-166 / 239-240.
    Returns (shortages, shipment_delivered, daily_demand, daily_delivered, daily_shortage).
    """
    fg_stock: dict[str, int] = dict(init_stock.get("fg_storage", {}))
    for sku in all_fg_skus:
        fg_stock.setdefault(sku, 0)

    demand_by_time: dict[int, dict[str, int]] = {}
    for d in demand_orders:
        t = int(d["start_time"])
        sku = d["sku"]
        qty = d["quantity"]
        if qty > 0 and sku in all_fg_skus:
            demand_by_time.setdefault(t, {})[sku] = (
                demand_by_time.get(t, {}).get(sku, 0) + qty
            )

    shipment_times = sorted(demand_by_time.keys())

    shortages: dict[str, int] = defaultdict(int)
    shipment_delivered: dict[str, int] = defaultdict(int)
    daily_demand: dict[int, int] = {}
    daily_delivered: dict[int, int] = {}
    daily_shortage: dict[int, int] = {}

    shipment_ptr = 0

    prod_by_shift: dict[int, list[LineAssignment]] = defaultdict(list)
    for a in fg_plan:
        prod_by_shift[a.shift_index].append(a)

    for shift in shifts:
        if shift.type == "day":
            ship_time = shift.start_time
            while (
                shipment_ptr < len(shipment_times)
                and shipment_times[shipment_ptr] == ship_time
            ):
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

        for a in prod_by_shift.get(shift.index, []):
            fg_stock[a.sku] = fg_stock.get(a.sku, 0) + a.quantity

    return shortages, shipment_delivered, daily_demand, daily_delivered, daily_shortage


def run_scip_global(
    shifts: list[Shift],
    init_stock: dict[str, dict[str, int]],
    demand_orders: list[dict],
    x_lines: list[str],
    line_skus: dict[str, list[str]],
    capacity: dict[str, dict[str, int]],
    all_fg_skus: set[str],
) -> tuple[
    list[LineAssignment],
    dict[str, int],
    dict[str, int],
    dict[int, int],
    dict[int, int],
    dict[int, int],
]:
    """Entry point for decision_mode == 5.

    Returns the same 6-tuple as planner_fg.run().
    """
    fg_plan = run_rolling_global(
        shifts,
        init_stock,
        demand_orders,
        x_lines,
        line_skus,
        capacity,
        all_fg_skus,
    )

    shortages, shipment_delivered, daily_demand, daily_delivered, daily_shortage = (
        simulate_fulfillment(
            shifts, demand_orders, fg_plan, init_stock, all_fg_skus
        )
    )

    return (
        fg_plan,
        shortages,
        shipment_delivered,
        daily_demand,
        daily_delivered,
        daily_shortage,
    )
