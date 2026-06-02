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


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    run_dir = sys.argv[1]
    report = build_report(run_dir)

    report_path = os.path.join(run_dir, "report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    s = report["summary"]
    print(f"  transport jobs: {s['transport_jobs_total']} ({s['transport_jobs_delayed']} delayed, {s['transport_jobs_incomplete']} incomplete)")
    print(f"  production jobs: {s['production_jobs_total']} ({s['production_jobs_delayed']} delayed, {s['production_jobs_incomplete']} incomplete)")
    print(f"Report written to: {report_path}")


if __name__ == "__main__":
    main()
