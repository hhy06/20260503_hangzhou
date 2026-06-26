"""Trace the full supply chain for one FG SKU and identify bottlenecks.

Usage:
    python trace_sku.py --sku 17AV081261H --run-dir scenario/srw_hangzhou1/run_YYYYMMDD_HHMMSS

Reads sim.jsonl from a completed simulation run and imports the scenario
module to resolve BOM / topology.  No simulation re-run needed.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_events(run_dir: Path, sku_filter: set[str] | None = None):
    events = []
    with open(run_dir / "sim.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            if sku_filter is not None:
                sku = rec.get("sku", "")
                if sku and sku not in sku_filter:
                    continue
            events.append(rec)
    return events


def import_scenario():
    import scenario.srw_hangzhou1.scenario_builder as sb
    import scenario.srw_hangzhou1.config as cfg
    import scenario.srw_hangzhou1.plant_topology as topo
    ctx = sb.create_simulation()
    mgmt = ctx.management
    return ctx, mgmt, cfg, topo


def build_sku_lines(mgmt):
    sku_lines = defaultdict(list)
    for ln, skus in mgmt._line_skus.items():
        for sku in skus:
            sku_lines[sku].append(ln)
    return sku_lines


def collect_subjects_for_sku(fg_sku, mgmt, sku_lines):
    """Return set of all subjects (node/edge names) relevant to tracing fg_sku."""
    subjects = set()
    fg_lines = sku_lines.get(fg_sku, [])
    for fl in fg_lines:
        subjects.add(fl)
        pnode = mgmt._production_nodes[fl]
        subjects.add(pnode.downstream_node.node_name)
        subjects.add(pnode.upstream_node.node_name)

    bom_chain_skus = set()
    bom_chain_skus.add(fg_sku)
    visited = set()
    stack = [fg_sku]
    while stack:
        sku = stack.pop()
        if sku in visited:
            continue
        visited.add(sku)
        lines = sku_lines.get(sku, [])
        for ln in lines:
            pnode = mgmt._production_nodes[ln]
            bom_entry = pnode.bom.get(sku)
            if bom_entry is None:
                continue
            for input_sku in bom_entry["inputs"]:
                bom_chain_skus.add(input_sku)
                stack.append(input_sku)
            subjects.add(ln)
            subjects.add(pnode.downstream_node.node_name)
            subjects.add(pnode.upstream_node.node_name)

    for edge in mgmt.edges:
        from_n = edge.from_node.node_name
        to_n = edge.to_node.node_name
        key = f"E({from_n} -> {to_n})"
        if from_n in subjects or to_n in subjects:
            subjects.add(key)

    sink_related = {"fg_storage", "sink"}
    subjects.update(sink_related)
    for n in mgmt.nodes:
        if n in ("fg_storage", "sink", "wip_storage", "veg_wip_storage",
                  "raw_material_storage", "prep_storage_1", "prep_storage_2",
                  "veg_raw_storage", "source"):
            subjects.add(n)

    return subjects, bom_chain_skus, fg_lines


def aggregate_production(events, line_name, sku):
    stats = defaultdict(int)
    total_qty = 0.0
    for rec in events:
        if rec.get("subject") != line_name or rec.get("sku") != sku:
            continue
        t = rec["type"]
        if t == "production_job_added":
            stats["orders_added"] += 1
        elif t == "production_started":
            stats["started"] += 1
        elif t == "production_completed":
            stats["completed"] += 1
            total_qty += rec.get("quantity", 0)
        elif t == "production_failed":
            stats["failed"] += 1
        elif t == "production_deferred":
            stats["deferred"] += 1
        elif t == "production_output":
            stats["output_batches"] += 1
    stats["total_qty"] = total_qty
    return stats


def aggregate_transport(events, edge_key, sku):
    stats = defaultdict(int)
    total_qty = 0.0
    for rec in events:
        if rec.get("subject") != edge_key or rec.get("sku") != sku:
            continue
        t = rec["type"]
        if t == "transport_order_added":
            stats["orders_added"] += 1
            stats["qty_added"] += rec.get("quantity", 0)
        elif t == "transport_started":
            stats["started"] += 1
            stats["qty_started"] += rec.get("quantity", 0)
        elif t == "transport_completed":
            stats["completed"] += 1
            stats["qty_completed"] += rec.get("quantity", 0)
            total_qty += rec.get("quantity", 0)
    stats["total_delivered"] = total_qty
    return stats


def aggregate_node_inventory(events, node_name, sku):
    received = 0
    debited = 0
    for rec in events:
        if rec.get("subject") != node_name or rec.get("sku") != sku:
            continue
        t = rec["type"]
        if t == "set_init":
            received += rec.get("quantity", 0)
        elif t == "received":
            received += rec.get("quantity", 0)
        elif t == "debited":
            debited += rec.get("quantity", 0)
    return {"received": received, "debited": debited, "net": received - debited}


def demand_stats(events, sku, sink_name="sink"):
    shipped = 0
    for rec in events:
        if rec.get("subject") == sink_name and rec.get("sku") == sku and rec["type"] == "received":
            shipped += rec.get("quantity", 0)
    return shipped


def trace_fg_sku(fg_sku, run_dir):
    ctx, mgmt, cfg, topo = import_scenario()
    sku_lines = build_sku_lines(mgmt)
    subjects, bom_chain_skus, fg_lines = collect_subjects_for_sku(fg_sku, mgmt, sku_lines)

    events = load_events(run_dir, bom_chain_skus)

    # Also load events for transport edges involving bom_chain_skus
    all_events = load_events(run_dir)
    transport_events = [r for r in all_events if r["type"].startswith("transport") and r.get("sku") in bom_chain_skus]
    all_rel_events = events + transport_events

    print(f"=== SKU Trace: {fg_sku} ===")
    print()

    fg_pnode = mgmt._production_nodes[fg_lines[0]]
    fg_line = fg_lines[0]
    bom_entry = fg_pnode.bom.get(fg_sku)

    shipped = demand_stats(all_events, fg_sku)
    fg_demand_total = sum(d["quantity"] for d in mgmt._demand_orders if d["sku"] == fg_sku)
    rate = shipped / fg_demand_total * 100 if fg_demand_total > 0 else 0

    print(f"DEMAND")
    print(f"  Total demand: {fg_demand_total:.0f} | Shipped to sink: {shipped:.0f} ({rate:.1f}%)")
    print(f"  Unshipped: {fg_demand_total - shipped:.0f}")
    print()

    prod = aggregate_production(all_rel_events, fg_line, fg_sku)
    print(f"FG PRODUCTION ({fg_line})")
    print(f"  Orders added: {prod['orders_added']} | Started: {prod['started']} | Completed: {prod['completed']}")
    print(f"  Failed: {prod['failed']} | Deferred: {prod['deferred']}")
    print(f"  Total produced qty: {prod['total_qty']:.0f}")

    out_node = fg_pnode.downstream_node.node_name
    out_inv = aggregate_node_inventory(all_events, out_node, fg_sku)
    print(f"  Output buffer ({out_node}): net={out_inv['net']:.0f} (received={out_inv['received']:.0f}, debited={out_inv['debited']:.0f})")
    if out_inv['net'] > 0:
        print(f"  ⚠ {out_inv['net']:.0f} units stuck in output buffer")
    print()

    fg_edge_key = f"E({out_node} -> fg_storage)"
    fg_transport = aggregate_transport(all_rel_events, fg_edge_key, fg_sku)
    print(f"FG TRANSPORT ({out_node} → fg_storage)")
    print(f"  Orders added: {fg_transport['orders_added']} | Started: {fg_transport['started']} | Completed: {fg_transport['completed']}")
    print(f"  Qty added: {fg_transport['qty_added']:.0f} | Delivered: {fg_transport['total_delivered']:.0f}")
    pending_qty = fg_transport['qty_added'] - fg_transport['qty_completed']
    if pending_qty > 0:
        print(f"  ⚠ {pending_qty:.0f} units in transit or pending")
    print()

    fg_inv = aggregate_node_inventory(all_events, "fg_storage", fg_sku)
    print(f"FG STORAGE (fg_storage, {fg_sku})")
    print(f"  Net: {fg_inv['net']:.0f} (received={fg_inv['received']:.0f}, debited={fg_inv['debited']:.0f})")
    print()

    if bom_entry is None:
        print("No BOM entry found for this SKU on its producing line.")
        return

    shift_dur = mgmt._per_line_info[fg_line]["shift_duration"]
    speed = bom_entry.get("speed", 0)
    if speed == 0:
        sku_obj = fg_pnode.sku_registry.get(fg_sku) if fg_pnode.sku_registry else None
        speed = sku_obj.bom_speed if sku_obj and sku_obj.bom_speed > 0 else 1.0
    capacity_per_shift = max(1, int(speed * shift_dur))

    lineside = fg_pnode.upstream_node.node_name
    prep = mgmt._fert_prep.get(fg_line)

    print(f"BOM INPUTS (per shift of {capacity_per_shift} units, line={fg_line}, lineside={lineside})")
    print(f"  {'SKU':<20} {'coeff':>8} {'per-shift':>10} {'at_lineside':>12} {'shortfall':>10}")
    print(f"  {'─'*20} {'─'*8} {'─'*10} {'─'*12} {'─'*10}")

    input_details = []
    for input_sku, qty_per in bom_entry["inputs"].items():
        per_shift = capacity_per_shift * qty_per
        lineside_inv = aggregate_node_inventory(all_events, lineside, input_sku)
        at_lineside = lineside_inv['net']
        shortfall = max(0, per_shift - at_lineside)
        is_wip = input_sku in sku_lines
        marker = " ⚠" if shortfall > per_shift * 0.5 else ""
        print(f"  {input_sku:<20} {qty_per:>8.5f} {per_shift:>10.1f} {at_lineside:>12.0f} {shortfall:>10.1f}{marker}")

        input_details.append({
            "sku": input_sku,
            "qty_per": qty_per,
            "per_shift": per_shift,
            "at_lineside": at_lineside,
            "shortfall": shortfall,
            "is_wip": is_wip,
        })

    print()

    for detail in input_details:
        input_sku = detail["sku"]
        is_wip = detail["is_wip"]
        marker = " ⚠" if detail["shortfall"] > detail["per_shift"] * 0.5 else ""

        if is_wip:
            wip_line_names = sku_lines.get(input_sku, [])
            wip_pool = mgmt._wip_pool.get(input_sku, "?")

            print(f"WIP PRODUCTION ({input_sku}, pool={wip_pool}){marker}")
            for wl in wip_line_names:
                wip_prod = aggregate_production(all_rel_events, wl, input_sku)
                if wip_prod["orders_added"] > 0 or wip_prod["completed"] > 0 or wip_prod["failed"] > 0:
                    print(f"  {wl}: added={wip_prod['orders_added']}, completed={wip_prod['completed']}, failed={wip_prod['failed']}, deferred={wip_prod['deferred']}, qty={wip_prod['total_qty']:.0f}")
            print()

            wip_pnode = mgmt._production_nodes[wip_line_names[0]]
            wip_out = wip_pnode.downstream_node.node_name

            print(f"WIP TRANSPORT ({input_sku})")
            hops = []
            if wip_pool != "?":
                hops.append((wip_out, wip_pool))
            if prep:
                if wip_pool != "?" and wip_pool != prep:
                    hops.append((wip_pool, prep))
                hops.append((prep, lineside))

            for from_n, to_n in hops:
                ekey = f"E({from_n} -> {to_n})"
                t_stats = aggregate_transport(all_rel_events, ekey, input_sku)
                pending = t_stats['qty_added'] - t_stats['qty_completed']
                pm = " ⚠" if pending > 0 else ""
                print(f"  {from_n} → {to_n}: added={t_stats['orders_added']}, completed={t_stats['completed']}, delivered={t_stats['total_delivered']:.0f}, pending={pending:.0f}{pm}")

            for node_n in [wip_out, wip_pool] if wip_pool != "?" else [wip_out]:
                inv = aggregate_node_inventory(all_events, node_n, input_sku)
                if inv['net'] != 0:
                    print(f"  {node_n} ({input_sku}): net={inv['net']:.0f}")
            print()

            wip_bom_entry = mgmt._production_nodes[wip_line_names[0]].bom.get(input_sku)
            if wip_bom_entry:
                wip_lineside = mgmt._production_nodes[wip_line_names[0]].upstream_node.node_name
                wip_capacity = mgmt._line_capacity[wip_line_names[0]].get(input_sku, 0)
                print(f"  WIP BOM inputs (per shift of {wip_capacity}, lineside={wip_lineside})")
                print(f"    {'SKU':<20} {'coeff':>8} {'per-shift':>10} {'at_lineside':>12}")
                for raw_sku, raw_qty_per in wip_bom_entry["inputs"].items():
                    raw_per_shift = wip_capacity * raw_qty_per
                    raw_inv = aggregate_node_inventory(all_events, wip_lineside, raw_sku)
                    print(f"    {raw_sku:<20} {raw_qty_per:>8.5f} {raw_per_shift:>10.1f} {raw_inv['net']:>12.0f}")
                print()

        else:
            print(f"RAW INPUT ({input_sku}){marker}")
            if prep:
                hops_raw = [("source", prep)]
                wip_pool_check = mgmt._wip_pool.get(input_sku)
                if wip_pool_check and wip_pool_check != prep:
                    hops_raw = [("source", wip_pool_check), (wip_pool_check, prep)]
                hops_raw.append((prep, lineside))

                for from_n, to_n in hops_raw:
                    ekey = f"E({from_n} -> {to_n})"
                    t_stats = aggregate_transport(all_rel_events, ekey, input_sku)
                    pending = t_stats['qty_added'] - t_stats['qty_completed']
                    pm = " ⚠" if pending > 0 else ""
                    print(f"  {from_n} → {to_n}: added={t_stats['orders_added']}, completed={t_stats['completed']}, delivered={t_stats['total_delivered']:.0f}, pending={pending:.0f}{pm}")

            print()

    print("BOTTLENECK SUMMARY")
    bottlenecks = []

    if out_inv['net'] > 0:
        bottlenecks.append(f"FG output buffer stuck: {out_inv['net']:.0f} units in {out_node}")

    if prod['deferred'] > 0:
        bottlenecks.append(f"FG production deferred: {prod['deferred']} orders on {fg_line}")

    if prod['failed'] > 0:
        bottlenecks.append(f"FG production failed: {prod['failed']} times on {fg_line}")

    for detail in input_details:
        if detail["shortfall"] > detail["per_shift"] * 0.5:
            bottlenecks.append(f"Insufficient {detail['sku']} at {lineside}: need {detail['per_shift']:.1f}/shift, have {detail['at_lineside']:.0f}")

    fg_shipped = fg_demand_total - shipped
    if fg_shipped > fg_demand_total * 0.3:
        bottlenecks.append(f"Low overall fulfillment: {rate:.1f}% of demand shipped")

    if bottlenecks:
        for i, b in enumerate(bottlenecks, 1):
            print(f"  {i}. {b}")
    else:
        print("  No significant bottlenecks detected")


def main():
    parser = argparse.ArgumentParser(description="Trace supply chain for one FG SKU")
    parser.add_argument("--sku", required=True, help="FG SKU ID to trace (e.g. 17AV081261H)")
    parser.add_argument("--run-dir", required=True, help="Path to completed run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not (run_dir / "sim.jsonl").exists():
        print(f"Error: sim.jsonl not found in {run_dir}")
        sys.exit(1)

    trace_fg_sku(args.sku, run_dir)


if __name__ == "__main__":
    main()
