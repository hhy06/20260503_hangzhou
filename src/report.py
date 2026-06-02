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

    with open(jsonl_path) as f:
        for line in f:
            rec = json.loads(line)
            t = rec.get("_type")

            if t == "order_issued":
                oid = rec.get("order_id")
                if oid is not None:
                    order_issued[oid] = rec

            elif t == "event":
                ev_type = rec.get("type")
                oid = rec.get("order_id")

                if ev_type == "transport_order_added" and oid is not None:
                    transport_added[oid] = rec

                elif ev_type == "transport_started" and oid is not None:
                    transport_starts[oid] = rec

                elif ev_type == "transport_completed" and oid is not None:
                    transport_ends[oid] = rec

                elif ev_type == "production_started" and oid is not None:
                    production_starts[oid] = rec

                elif ev_type == "production_completed" and oid is not None:
                    production_ends[oid] = rec

                elif ev_type in ("received", "debited"):
                    storage_events.append(rec)

    storage_events.sort(key=lambda e: e.get("time", 0.0))

    # --- Build transport jobs ---
    all_transport_order_ids: set[int] = set()
    for oid_rec in order_issued.values():
        if oid_rec.get("order_type") == "transport":
            all_transport_order_ids.add(oid_rec["order_id"])
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
    all_prod_order_ids: set[int] = set()
    for oid_rec in order_issued.values():
        if oid_rec.get("order_type") == "production":
            all_prod_order_ids.add(oid_rec["order_id"])
    all_prod_order_ids.update(production_starts.keys())
    all_prod_order_ids.update(production_ends.keys())

    production_jobs = []
    for oid in sorted(all_prod_order_ids):
        issued = order_issued.get(oid)
        started_ev = production_starts.get(oid)
        ended_ev = production_ends.get(oid)

        job = {"order_id": oid}

        # Fields from order_issued
        src = issued or {}
        job["sku"] = src.get("sku")
        job["quantity"] = src.get("quantity")
        job["node"] = src.get("node_name")
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


def write_text_report(run_dir: str) -> str:
    """Write per-node/edge report.txt with issued/started counts.

    Returns the path to the created file.
    """
    jsonl_path = os.path.join(run_dir, "sim.jsonl")
    meta_path = os.path.join(run_dir, "meta.json")

    meta = {}
    if os.path.isfile(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)

    # Counters per component
    edge_issued: dict[str, int] = {}    # transport_order_added events
    edge_started: dict[str, int] = {}   # transport_started events
    prod_issued: dict[str, int] = {}    # order_issued (production) by node_name
    prod_started: dict[str, int] = {}   # production_started events
    storage_received: dict[str, int] = {}
    storage_debited: dict[str, int] = {}

    with open(jsonl_path) as f:
        for line in f:
            rec = json.loads(line)
            t = rec.get("_type")

            if t == "order_issued":
                if rec.get("order_type") == "production":
                    node = rec.get("node_name")
                    if node:
                        prod_issued[node] = prod_issued.get(node, 0) + 1

            elif t == "event":
                ev_type = rec.get("type")
                node = rec.get("node")

                if ev_type == "transport_order_added":
                    edge_issued[node] = edge_issued.get(node, 0) + 1
                elif ev_type == "transport_started":
                    edge_started[node] = edge_started.get(node, 0) + 1
                elif ev_type == "production_started":
                    prod_started[node] = prod_started.get(node, 0) + 1
                elif ev_type == "received":
                    storage_received[node] = storage_received.get(node, 0) + 1
                elif ev_type == "debited":
                    storage_debited[node] = storage_debited.get(node, 0) + 1

    scenario = meta.get("scenario", "")
    mgmt = meta.get("management_type", "")
    duration = meta.get("sim_duration", "")

    lines: list[str] = []
    lines.append(f"=== {scenario} ({mgmt}, {duration} min) ===")
    lines.append("")

    # --- Transport edges ---
    edge_names = sorted(set(edge_issued) | set(edge_started))
    lines.append(f"{'=== Transport Edges ===':<80}")
    lines.append(f"{'edge':<50} {'issued':>8} {'started':>8}")
    lines.append("-" * 80)
    for name in edge_names:
        i = edge_issued.get(name, 0)
        s = edge_started.get(name, 0)
        lines.append(f"{name:<50} {i:>8} {s:>8}")
    lines.append("")

    # --- Production nodes ---
    prod_names = sorted(set(prod_issued) | set(prod_started))
    if prod_names:
        lines.append(f"{'=== Production Nodes ===':<80}")
        lines.append(f"{'node':<50} {'issued':>8} {'started':>8}")
        lines.append("-" * 80)
        for name in prod_names:
            i = prod_issued.get(name, 0)
            s = prod_started.get(name, 0)
            lines.append(f"{name:<50} {i:>8} {s:>8}")
        lines.append("")

    # --- Storage nodes ---
    storage_names = sorted(set(storage_received) | set(storage_debited))
    if storage_names:
        lines.append(f"{'=== Storage Nodes ===':<80}")
        lines.append(f"{'node':<50} {'received':>10} {'debited':>10}")
        lines.append("-" * 80)
        for name in storage_names:
            r = storage_received.get(name, 0)
            d = storage_debited.get(name, 0)
            lines.append(f"{name:<50} {r:>10} {d:>10}")
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
