"""SETA — Simulation Event Trace Analyzer.

Transforms raw discrete-event trace records (sim.jsonl + meta.json)
into a navigable, merged HTML report.
"""

import argparse
import sys
import os

from src.seta.processor import process_run
from src.seta.renderer import render_report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: process a run directory and generate an HTML report."""
    ap = argparse.ArgumentParser(
        description="Generate a SETA report from a simulation run directory."
    )
    ap.add_argument(
        "run_dir",
        help="Path to a simulation run directory containing meta.json and sim.jsonl",
    )
    ap.add_argument(
        "-o", "--output",
        default="seta_report.html",
        help="Output HTML file path (default: seta_report.html)",
    )
    args = ap.parse_args(argv)

    run_dir = os.path.abspath(args.run_dir)
    if not os.path.isdir(run_dir):
        print(f"Error: run directory not found: {run_dir}", file=sys.stderr)
        return 1

    meta_path = os.path.join(run_dir, "meta.json")
    sim_path = os.path.join(run_dir, "sim.jsonl")
    if not os.path.isfile(meta_path) or not os.path.isfile(sim_path):
        print(f"Error: {run_dir} must contain both meta.json and sim.jsonl", file=sys.stderr)
        return 1

    print(f"Processing: {run_dir}")
    data = process_run(run_dir)

    meta = data["meta"]
    print(f"  Scenario: {meta['scenario']}")
    print(f"  Duration: {meta['sim_duration']:g}")
    print(f"  Nodes: {meta['num_nodes']}, Edges: {meta['num_edges']}")
    print(f"  Raw events: {meta['event_count']}")
    merged_count = sum(len(n["events"]) for n in data["nodes"].values())
    merged_count += sum(len(e["events"]) for e in data["edges"].values())
    print(f"  Merged summaries: {merged_count}")
    print(f"  Orders: {meta['order_count']}")

    print(f"Rendering report: {args.output}")
    out = render_report(data, args.output)
    print(f"Done: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
