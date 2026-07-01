"""PSP Planner — shift-level production planning without simulation.

Usage:
    python psp_main.py [scenario_name] [num_days] [--mode 1|2|3]
"""

import sys
from pathlib import Path

import pandas as pd

from src.psp.planner import run_plan
from src.psp.output import write


SCENARIO_MAP = {
    "psp": "scenario/psp",
    "srw_hangzhou1": "scenario/srw_hangzhou1",
    "srw_hangzhou1_90d": "scenario/srw_hangzhou1_90d",
    "srw_hangzhou1_oneyear": "scenario/srw_hangzhou1_oneyear",
}


def main():
    args = sys.argv[1:]
    scenario_key = args[0] if len(args) > 0 and args[0] not in ("--mode",) else "psp"
    num_days = int(args[1]) if len(args) > 1 and args[1] not in ("--mode",) else 30

    decision_mode = 1
    for i, a in enumerate(args):
        if a == "--mode" and i + 1 < len(args):
            decision_mode = int(args[i + 1])

    rel_path = SCENARIO_MAP.get(scenario_key, scenario_key)
    scenario_path = Path(__file__).resolve().parent / rel_path

    if not scenario_path.exists():
        print(f"Scenario not found: {scenario_path}")
        sys.exit(1)

    print(f"[PSP] Decision mode: {decision_mode}")
    plan = run_plan(scenario_path, num_days, decision_mode=decision_mode)

    sku_xlsx = scenario_path / "skus.xlsx"
    sku_name_map: dict[str, str] = {}
    if sku_xlsx.exists():
        sku_df = pd.read_excel(sku_xlsx, sheet_name="SKUS")
        sku_name_map = dict(zip(sku_df["sku_id"].astype(str), sku_df["name"].astype(str)))
    write(plan, scenario_path, sku_name_map=sku_name_map)


if __name__ == "__main__":
    main()
