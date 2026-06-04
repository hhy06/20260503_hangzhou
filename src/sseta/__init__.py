"""SSETA — Static Simulation Event Trace Analyzer.

Generates a static PDF report with node/edge diagrams.
"""

import argparse
import os
import sys

from src.seta.processor import process_run
from src.sseta.renderer import render_pdf


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate a static PDF SETA report.")
    ap.add_argument("run_dir", help="Simulation run directory")
    ap.add_argument("-o", "--output", default="report.pdf", help="Output PDF path")
    args = ap.parse_args(argv)

    run_dir = os.path.abspath(args.run_dir)
    if not os.path.isdir(run_dir):
        print(f"Error: not a directory: {run_dir}", file=sys.stderr)
        return 1

    print(f"Processing data from: {run_dir}")
    data = process_run(run_dir)

    print(f"Generating PDF report: {args.output}")
    render_pdf(data, args.output)
    print(f"Done: {args.output}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
