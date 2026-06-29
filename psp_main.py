"""PSP Planner — shift-level production planning without simulation.

Usage:
    python psp_main.py [scenario_name] [num_days]
"""

import sys
from pathlib import Path

from src.psp.planner import run_plan
from src.psp.output import write


SCENARIO_MAP = {
    "psp": "scenario/psp",
    "srw_hangzhou1": "scenario/srw_hangzhou1",
    "srw_hangzhou1_90d": "scenario/srw_hangzhou1_90d",
    "srw_hangzhou1_oneyear": "scenario/srw_hangzhou1_oneyear",
}


def main():
    scenario_key = sys.argv[1] if len(sys.argv) > 1 else "psp"
    num_days = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    rel_path = SCENARIO_MAP.get(scenario_key, scenario_key)
    scenario_path = Path(__file__).resolve().parent / rel_path

    if not scenario_path.exists():
        print(f"Scenario not found: {scenario_path}")
        sys.exit(1)

    plan = run_plan(scenario_path, num_days)
    write(plan, scenario_path)


if __name__ == "__main__":
    main()
