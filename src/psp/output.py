"""Write PSP plan results to run directory."""

import csv
from datetime import datetime
from pathlib import Path

from src.psp.types import PspPlan


def write(plan: PspPlan, scenario_path: Path) -> Path:
    run_dir = scenario_path / f"run_psp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    with open(run_dir / "fg_plan.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["shift_index", "day", "shift_type", "line_id", "sku", "quantity", "feasible"])
        for a in plan.fg_assignments:
            s = plan.shifts[a.shift_index]
            w.writerow([a.shift_index, s.day, s.type, a.line_id, a.sku, a.quantity, int(a.feasible)])

    with open(run_dir / "wip_plan.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["shift_index", "day", "shift_type", "line_id", "sku", "quantity"])
        for a in plan.wip_assignments:
            s = plan.shifts[a.shift_index]
            w.writerow([a.shift_index, s.day, s.type, a.line_id, a.sku, a.quantity])

    with open(run_dir / "material_orders.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["shift_index", "day", "shift_type", "sku", "quantity", "target_warehouse"])
        for o in plan.material_orders:
            s = plan.shifts[o.shift_index]
            w.writerow([o.shift_index, s.day, s.type, o.sku, round(o.quantity, 4), o.target_warehouse])

    with open(run_dir / "daily_report.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["day", "demand_qty", "fg_produced", "fg_delivered", "fg_shortage",
                     "fg_short_pct", "wip_needed", "wip_produced"])
        cum_fg = plan.init_fg_stock
        cum_wip_needed = 0
        cum_wip_produced = 0
        for r in plan.daily_report:
            cum_fg += r["fg_produced"] - r["fg_delivered"]
            cum_wip_needed += r["wip_needed"]
            cum_wip_produced += r["wip_produced"]
            w.writerow([
                r["day"],
                r["demand_qty"],
                r["fg_produced"],
                r["fg_delivered"],
                r["fg_shortage"],
                r["fg_short_pct"],
                r["wip_needed"],
                r["wip_produced"],
            ])

    with open(run_dir / "summary.txt", "w") as f:
        f.write("=== PSP Plan Summary ===\n\n")
        total_demand = sum(plan.shortages.values()) + sum(plan.shipment_delivered.values())
        total_delivered = sum(plan.shipment_delivered.values())
        f.write(f"Shifts planned: {len(plan.shifts)}\n")
        f.write(f"Days planned: {plan.shifts[-1].day}\n" if plan.shifts else "Days planned: 0\n")
        f.write(f"\nFG assignments: {len(plan.fg_assignments)}\n")
        f.write(f"WIP assignments: {len(plan.wip_assignments)}\n")
        f.write(f"Material orders: {len(plan.material_orders)}\n")
        f.write(f"\nInitial FG stock: {plan.init_fg_stock:,}\n")
        f.write(f"Total demand: {total_demand:,}\n")
        f.write(f"Total delivered: {total_delivered:,}\n")
        total_short = sum(plan.shortages.values())
        if total_demand > 0:
            pct = 100.0 * total_delivered / total_demand
            f.write(f"Fulfillment rate: {pct:.2f}%\n")
            short_pct = 100.0 * total_short / total_demand
            f.write(f"FG shortage ratio: {short_pct:.2f}%\n")
        else:
            f.write("Fulfillment rate: N/A (no demand)\n")

        if plan.shortages:
            f.write(f"\nShortages ({len(plan.shortages)} SKUs):\n")
            sorted_shortages = sorted(plan.shortages.items(), key=lambda x: -x[1])[:30]
            for sku, qty in sorted_shortages:
                f.write(f"  {sku}: {qty:,}\n")
            if len(plan.shortages) > 30:
                f.write(f"  ... +{len(plan.shortages) - 30} more\n")

        fg_qty = sum(a.quantity for a in plan.fg_assignments)
        wip_qty = sum(a.quantity for a in plan.wip_assignments)
        f.write(f"\nProduction volumes:\n")
        f.write(f"  FG total: {fg_qty:,}\n")
        f.write(f"  WIP total: {wip_qty:,}\n")

        f.write(f"\n=== Daily Report ===\n")
        f.write(f"{'Day':>4} {'Demand':>10} {'FG_Prod':>10} {'FG_Delv':>10} {'Short':>8} "
                f"{'Short%':>7} {'WIP_Need':>10} {'WIP_Prod':>10}\n")
        f.write(f"{'─'*4} {'─'*10} {'─'*10} {'─'*10} {'─'*8} {'─'*7} {'─'*10} {'─'*10}\n")
        cum_fg = plan.init_fg_stock
        for r in plan.daily_report:
            cum_fg += r["fg_produced"] - r["fg_delivered"]
            d = r["demand_qty"]
            fp = r["fg_produced"]
            fd = r["fg_delivered"]
            fs = r["fg_shortage"]
            sp = r["fg_short_pct"]
            wn = r["wip_needed"]
            wp = r["wip_produced"]
            f.write(f"{r['day']:>4d} {d:>10,} {fp:>10,} {fd:>10,} {fs:>8,} "
                    f"{sp:>6.2f}% {wn:>10,} {wp:>10,}\n")

    print(f"[PSP] Results written to {run_dir}")
    return run_dir
