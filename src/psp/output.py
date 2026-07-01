"""Write PSP plan results to run directory."""

import csv
from datetime import datetime
from pathlib import Path

from src.psp.types import PspPlan


def write(plan: PspPlan, scenario_path: Path, sku_name_map: dict[str, str] | None = None) -> Path:
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

    with open(run_dir / "material_movement.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["shift_index", "day", "shift_type", "from_node", "to_node",
                     "sku", "sku_name", "quantity", "movement_type"])
        for m in plan.movements:
            s = plan.shifts[m.shift_index]
            sku_name = (sku_name_map or {}).get(m.sku, "")
            w.writerow([m.shift_index, s.day, s.type, m.from_node, m.to_node,
                        m.sku, sku_name, round(m.quantity, 4), m.movement_type])

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

        # ── Material Movement Summary (pallets) ─────────────────────
        if plan.daily_report and "source_out_pallets" in plan.daily_report[0]:
            f.write(f"\n=== Material Movement Summary (pallets) ===\n")
            wh_nodes = ["raw_material_storage", "veg_raw_storage", "wip_storage",
                        "veg_wip_storage", "prep_storage_1", "prep_storage_2", "fg_storage"]
            header = (f"{'Day':>4} {'SrcOut':>8} {'Consumed':>9}"
                      f" {'raw_mat':>8} {'veg_raw':>8} {'wip':>8} {'veg_wip':>8}"
                      f" {'prep_1':>8} {'prep_2':>8} {'fg':>8}  {'Shortage':>14}")
            f.write(header + "\n")
            sep = "─" * 4 + " " + "─" * 8 + " " + "─" * 9
            for _ in wh_nodes:
                sep += " " + "─" * 8
            sep += "  " + "─" * 14
            f.write(sep + "\n")
            for r in plan.daily_report:
                inv = r.get("inventory", {})
                shortage_str = ",".join(r.get("shortage_nodes", []))[:14] or ""
                f.write(f"{r['day']:>4d} {r['source_out_pallets']:>8,} {r['consumed_pallets']:>9,}"
                        f" {inv.get('raw_material_storage', 0):>8,} {inv.get('veg_raw_storage', 0):>8,}"
                        f" {inv.get('wip_storage', 0):>8,} {inv.get('veg_wip_storage', 0):>8,}"
                        f" {inv.get('prep_storage_1', 0):>8,} {inv.get('prep_storage_2', 0):>8,}"
                        f" {inv.get('fg_storage', 0):>8,}  {shortage_str:>14}\n")

    print(f"[PSP] Results written to {run_dir}")
    return run_dir
