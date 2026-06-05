"""Unified JSON Lines output writer for simulation results.

Produces a single ``sim.jsonl`` file with records collected from
nodes and edges.  Every record carries a ``subject`` field — the
responsible node or edge ID.

A companion ``meta.json`` file provides summary metadata.
"""

import datetime
import json
import os
import sys
from typing import Any

from src.infrastructure.warehouse_node import NodeRole


def _scenario_filepath(scenario_module_name: str) -> str:
    """Convert a dotted module name (``scenario.foo``) to a filesystem path."""
    parts = scenario_module_name.split(".")
    for base in sys.path:
        candidate = os.path.join(base, *parts)
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(*parts)


def write_output(
    scenario_name: str,
    nodes: dict[str, Any],
    edges: list[Any],
    management: Any,
    sim_duration: float,
    management_type: str,
    decision_interval: float,
) -> str:
    """Write unified JSON Lines output + meta.json, return the run directory.

    Parameters
    ----------
    scenario_name : str
        Dotted module path (e.g. ``scenario.ss_hangzhou0b``).
    nodes : dict[str, Any]
        All simulation nodes keyed by name.
    edges : list[Edge]
        All simulation edges.
    management : Management
        Management component (``.log`` is **not** used — order events are
        emitted by nodes/edges directly).
    sim_duration : float
        Total simulation duration in minutes.
    management_type : str
        Short string identifier.
    decision_interval : float
        Minutes between management decision cycles.

    Returns
    -------
    str
        Absolute path to the created run directory.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    scenario_path = _scenario_filepath(scenario_name)
    run_dir = os.path.join(scenario_path, f"run_{timestamp}")
    os.makedirs(run_dir, exist_ok=True)

    records: list[dict] = []

    # --- 1. Initial state (t=0 warehouse / source inventories) ---
    for name, node in nodes.items():
        if hasattr(node, "role") and hasattr(node, "inventory"):
            if node.role in (NodeRole.WAREHOUSE, NodeRole.SOURCE):
                for sku, qty in node.inventory.items():
                    records.append({
                        "type": "set_init",
                        "time": 0.0,
                        "subject": name,
                        "node": name,
                        "sku": sku,
                        "quantity": qty,
                    })

    # --- 2. Event records from all nodes ---
    for name, node in nodes.items():
        if hasattr(node, "log"):
            records.extend(node.log)

    # --- 3. Event records from all edges ---
    for edge in edges:
        records.extend(edge.log)

    # --- 4. Sort chronologically ---
    records.sort(key=lambda r: r.get("time", 0.0))

    # --- 5. Write sim.jsonl ---
    jsonl_path = os.path.join(run_dir, "sim.jsonl")
    with open(jsonl_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec, default=str, ensure_ascii=False) + "\n")

    # --- 6. Write meta.json ---
    order_count = sum(1 for r in records if r.get("type") in (
        "transport_order_added", "production_job_added",
    ))
    event_count = len(records) - order_count - sum(
        1 for r in records if r.get("type") == "set_init"
    )
    meta = {
        "scenario": scenario_name,
        "started_at": datetime.datetime.now().isoformat(),
        "sim_duration": sim_duration,
        "management_type": management_type,
        "decision_interval": decision_interval,
        "num_nodes": len(nodes),
        "num_edges": len(edges),
        "event_count": event_count,
        "order_count": order_count,
    }
    meta_path = os.path.join(run_dir, "meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return run_dir
