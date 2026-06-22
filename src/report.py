"""Generate report.json from sim.jsonl.

Usage:
    python3 -m src.report <run-dir>

Reads ``sim.jsonl`` and ``meta.json`` from the run directory, produces
``report.json`` with three sections:

- ``transport_jobs``: matched transport_started / transport_completed by order_id
- ``production_jobs``: matched production_started / production_completed by order_id
- ``storage_events``: chronological received / debited events on storage nodes
"""

import json
import os
import sys


def build_report(run_dir: str) -> dict:
    jsonl_path = os.path.join(run_dir, "sim.jsonl")
    meta_path = os.path.join(run_dir, "meta.json")

    if not os.path.isfile(jsonl_path):
        raise FileNotFoundError(f"sim.jsonl not found in {run_dir}")

    # --- Read meta ---
    meta = {}
    if os.path.isfile(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)

    # --- Parse sim.jsonl ---
    order_issued: dict[int, dict] = {}          # order_id → order_issued record
    transport_added: dict[int, dict] = {}        # order_id → transport_order_added
    transport_starts: dict[int, dict] = {}        # order_id → transport_started event
    transport_ends: dict[int, dict] = {}          # order_id → transport_completed event
    production_starts: dict[int, dict] = {}       # order_id → production_started event
    production_ends: dict[int, dict] = {}         # order_id → production_completed event
    storage_events: list[dict] = []

    # sim.jsonl uses a flat `type` field (e.g., "transport_started",
    # "production_completed", "set_init").  No nested `_type` wrapper.
    with open(jsonl_path) as f:
        for line in f:
            rec = json.loads(line)
            ev_type = rec.get("type")
            oid = rec.get("order_id")

            if ev_type == "transport_order_added" and oid is not None:
                transport_added[oid] = rec

            elif ev_type == "transport_started" and oid is not None:
                transport_starts[oid] = rec

            elif ev_type == "transport_completed" and oid is not None:
                transport_ends[oid] = rec

            elif ev_type == "production_job_added" and oid is not None:
                order_issued[oid] = rec

            elif ev_type == "production_started" and oid is not None:
                production_starts[oid] = rec

            elif ev_type == "production_completed" and oid is not None:
                production_ends[oid] = rec

            elif ev_type in ("received", "debited"):
                storage_events.append(rec)

    storage_events.sort(key=lambda e: e.get("time", 0.0))

    # --- Build transport jobs ---
    # Union of all transport-related order_ids (transport_order_added is the
    # primary key since management issues orders via add_transport_order)
    all_transport_order_ids: set[int] = set()
    all_transport_order_ids.update(transport_added.keys())
    all_transport_order_ids.update(transport_starts.keys())
    all_transport_order_ids.update(transport_ends.keys())

    transport_jobs = []
    for oid in sorted(all_transport_order_ids):
        issued = order_issued.get(oid)
        added = transport_added.get(oid)
        started_ev = transport_starts.get(oid)
        ended_ev = transport_ends.get(oid)

        job = {"order_id": oid}

        # Fields from order_issued (authoritative), fallback to transport_order_added
        src = issued or added or {}
        job["sku"] = src.get("sku")
        job["quantity"] = src.get("quantity")
        job["from_node"] = src.get("from_node") or src.get("from")
        job["to_node"] = src.get("to_node") or src.get("to")
        job["expect_time"] = src.get("expect_time")
        job["earliest_start_time"] = src.get("start_time")

        job["start_time"] = started_ev.get("time") if started_ev else None
        job["end_time"] = ended_ev.get("time") if ended_ev else None
        job["pallets"] = started_ev.get("pallets") if started_ev else None

        # Delayed: actual start > expected start
        if job["start_time"] is not None and job["expect_time"] is not None:
            job["delayed"] = job["start_time"] > job["expect_time"]
        else:
            job["delayed"] = None

        transport_jobs.append(job)

    # --- Build production jobs ---
    # Union of all production-related order_ids (production_job_added is the
    # primary key)
    all_prod_order_ids: set[int] = set()
    all_prod_order_ids.update(order_issued.keys())
    all_prod_order_ids.update(production_starts.keys())
    all_prod_order_ids.update(production_ends.keys())

    production_jobs = []
    for oid in sorted(all_prod_order_ids):
        issued = order_issued.get(oid)
        started_ev = production_starts.get(oid)
        ended_ev = production_ends.get(oid)

        job = {"order_id": oid}

        # Fields from production_job_added (order_issued), fallback to events
        src = issued or started_ev or {}
        job["sku"] = src.get("sku")
        job["quantity"] = src.get("quantity")
        job["node"] = src.get("node_name") or src.get("subject")
        job["expect_time"] = src.get("expect_time")
        job["activate_time"] = src.get("activate_time")

        job["start_time"] = started_ev.get("time") if started_ev else None
        job["end_time"] = ended_ev.get("time") if ended_ev else None

        # bom_speed from production_started event
        bom_speed = started_ev.get("bom_speed") if started_ev else None
        job["bom_speed"] = bom_speed

        if bom_speed is not None and job["quantity"] is not None:
            job["theoretical_duration"] = job["quantity"] / bom_speed
        else:
            job["theoretical_duration"] = None

        if job["start_time"] is not None and job["end_time"] is not None:
            job["actual_duration"] = job["end_time"] - job["start_time"]
        else:
            job["actual_duration"] = None

        # Delayed: same logic — actual start > expected start
        if job["start_time"] is not None and job["expect_time"] is not None:
            job["delayed"] = job["start_time"] > job["expect_time"]
        else:
            job["delayed"] = None

        production_jobs.append(job)

    # --- Summary ---
    delayed_transport = sum(
        1 for j in transport_jobs if j.get("delayed") is True
    )
    incomplete_transport = sum(
        1 for j in transport_jobs if j["end_time"] is None
    )
    delayed_production = sum(
        1 for j in production_jobs if j.get("delayed") is True
    )
    incomplete_production = sum(
        1 for j in production_jobs if j["end_time"] is None
    )

    report = {
        "meta": meta,
        "summary": {
            "transport_jobs_total": len(transport_jobs),
            "transport_jobs_delayed": delayed_transport,
            "transport_jobs_incomplete": incomplete_transport,
            "production_jobs_total": len(production_jobs),
            "production_jobs_delayed": delayed_production,
            "production_jobs_incomplete": incomplete_production,
        },
        "transport_jobs": transport_jobs,
        "production_jobs": production_jobs,
        "storage_events": storage_events,
    }

    return report


def _inc(key: str, d: dict[str, int], val: int = 1):
    d[key] = d.get(key, 0) + val


def write_text_report(run_dir: str) -> str:
    """Write per-node/edge report.txt with issued/started counts and amounts.

    Returns the path to the created file.
    """
    jsonl_path = os.path.join(run_dir, "sim.jsonl")
    meta_path = os.path.join(run_dir, "meta.json")

    meta = {}
    if os.path.isfile(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)

    # --- Edge counters ---
    edge_issued_cnt: dict[str, int] = {}
    edge_started_cnt: dict[str, int] = {}
    edge_issued_pallets: dict[str, int] = {}
    edge_started_pallets: dict[str, int] = {}

    # --- Production counters ---
    prod_issued_cnt: dict[str, int] = {}
    prod_started_cnt: dict[str, int] = {}
    prod_issued_qty: dict[str, int] = {}
    prod_started_qty: dict[str, int] = {}

    # --- Storage counters (pallets only) ---
    storage_pallets_in: dict[str, int] = {}
    storage_pallets_out: dict[str, int] = {}

    with open(jsonl_path) as f:
        for line in f:
            rec = json.loads(line)
            ev_type = rec.get("type")

            if ev_type == "transport_order_added":
                node = rec.get("subject")
                if node:
                    _inc(node, edge_issued_cnt)
                    _inc(node, edge_issued_pallets, rec.get("pallets", 0))

            elif ev_type == "transport_started":
                node = rec.get("subject")
                if node:
                    _inc(node, edge_started_cnt)
                    _inc(node, edge_started_pallets, rec.get("pallets", 0))

            elif ev_type == "production_started":
                node = rec.get("subject")
                if node:
                    _inc(node, prod_started_cnt)
                    _inc(node, prod_started_qty, rec.get("quantity", 0))

            elif ev_type == "received":
                node = rec.get("subject")
                if node:
                    _inc(node, storage_pallets_in, rec.get("pallets", 0))

            elif ev_type == "debited":
                node = rec.get("subject")
                if node:
                    _inc(node, storage_pallets_out, rec.get("pallets", 0))

    scenario = meta.get("scenario", "")
    mgmt = meta.get("management_type", "")
    duration = meta.get("sim_duration", "")

    lines: list[str] = []
    lines.append(f"=== {scenario} ({mgmt}, {duration} min) ===")
    lines.append("")

    def _pct(a: int, b: int) -> str:
        return f"{100.0 * b / a:>6.1f}%" if a else "    -"

    # --- Transport edges ---
    edge_names = sorted(set(edge_issued_cnt) | set(edge_started_cnt))
    lines.append(f"{'=== Transport Edges ===':<80}")
    lines.append(f"{'edge':<50} {'issued':>8} {'started':>8} {'started%':>8}  {'pallets_issued':>14} {'pallets_started':>15} {'started%':>8}")
    lines.append("-" * 120)
    for name in edge_names:
        ic = edge_issued_cnt.get(name, 0)
        sc = edge_started_cnt.get(name, 0)
        ip = edge_issued_pallets.get(name, 0)
        sp = edge_started_pallets.get(name, 0)
        lines.append(f"{name:<50} {ic:>8} {sc:>8} {_pct(ic, sc):>8}  {ip:>14} {sp:>15} {_pct(ip, sp):>8}")
    lines.append("")

    # --- Production nodes ---
    prod_names = sorted(set(prod_issued_cnt) | set(prod_started_cnt))
    if prod_names:
        lines.append(f"{'=== Production Nodes ===':<80}")
        lines.append(f"{'node':<50} {'issued':>8} {'started':>8} {'started%':>8}  {'qty_issued':>12} {'qty_started':>13} {'started%':>8}")
        lines.append("-" * 120)
        for name in prod_names:
            ic = prod_issued_cnt.get(name, 0)
            sc = prod_started_cnt.get(name, 0)
            iq = prod_issued_qty.get(name, 0)
            sq = prod_started_qty.get(name, 0)
            lines.append(f"{name:<50} {ic:>8} {sc:>8} {_pct(ic, sc):>8}  {iq:>12} {sq:>13} {_pct(iq, sq):>8}")
        lines.append("")

    # --- Storage nodes ---
    storage_names = sorted(set(storage_pallets_in) | set(storage_pallets_out))
    if storage_names:
        lines.append(f"{'=== Storage Nodes (pallets) ===':<80}")
        lines.append(f"{'node':<50} {'pallets_in':>12} {'pallets_out':>13}")
        lines.append("-" * 80)
        for name in storage_names:
            pi = storage_pallets_in.get(name, 0)
            po = storage_pallets_out.get(name, 0)
            lines.append(f"{name:<50} {pi:>12} {po:>13}")
        lines.append("")

    report_txt = "\n".join(lines)
    txt_path = os.path.join(run_dir, "report.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_txt)

    return txt_path


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    run_dir = sys.argv[1]
    report = build_report(run_dir)

    report_path = os.path.join(run_dir, "report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    txt_path = write_text_report(run_dir)

    s = report["summary"]
    print(f"  transport jobs: {s['transport_jobs_total']} ({s['transport_jobs_delayed']} delayed, {s['transport_jobs_incomplete']} incomplete)")
    print(f"  production jobs: {s['production_jobs_total']} ({s['production_jobs_delayed']} delayed, {s['production_jobs_incomplete']} incomplete)")
    print(f"  Report JSON: {report_path}")
    print(f"  Report TXT:  {txt_path}")


if __name__ == "__main__":
    main()
