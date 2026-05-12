"""Main simulation entry point.

Usage:
    python main.py                 → runs scenario1
    python main.py scenario1       → runs scenario1
    python main.py scenario_production → runs production scenario
"""

import importlib
from dataclasses import dataclass, field
from typing import Any
import sys

import salabim as sim

from src.edge import Edge
from src.warehouse_node import WarehouseNode, NodeRole
from src.management import JobManager
from src.production_node import ProductionNode


# ---------------------------------------------------------------------------
# Simulation result (returned by run_scenario for programmatic inspection)
# ---------------------------------------------------------------------------

@dataclass
class SimulationResult:
    """Holds the final state and event log after a simulation run.

    Access pattern:
        result.warehouse_inventories  -> {node_name: {sku: qty}}
        result.sink_received          -> {sink_name: {sku: qty}}
        result.all_logs               -> sorted list of {node, time, type, ...}
    """
    scenario_name: str
    nodes: dict[str, Any]
    config: Any

    @property
    def warehouse_inventories(self) -> dict[str, dict[str, int]]:
        return {
            name: dict(node.inventory)
            for name, node in self.nodes.items()
            if hasattr(node, 'role') and node.role == NodeRole.WAREHOUSE
        }

    @property
    def sink_received(self) -> dict[str, dict[str, int]]:
        return {
            name: dict(node.received)
            for name, node in self.nodes.items()
            if hasattr(node, 'role') and node.role == NodeRole.SINK
        }

    @property
    def all_logs(self) -> list[dict]:
        """All log entries from all nodes, sorted by simulation time."""
        logs: list[dict] = []
        for name, node in self.nodes.items():
            if hasattr(node, 'log'):
                for entry in node.log:
                    logs.append({"node": name, **entry})
        logs.sort(key=lambda x: x["time"])
        return logs


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------

def build_nodes(config, env: sim.Environment) -> dict[str, Any]:
    """Build all nodes in two passes:

    1. Source / warehouse / sink nodes (WarehouseNode).
    2. Production nodes (ProductionNode) — requires warehouses to exist.
    """
    nodes: dict[str, Any] = {}

    # -- Pass 1: warehouse-class nodes --------------------------------------
    for node_name, cfg in config.NODES.items():
        ntype = cfg["type"]
        if ntype in ("source", "warehouse", "sink"):
            cf = dict(config.PALLET_SIZE)
            node = WarehouseNode(
                name=node_name,
                role=NodeRole(ntype),
                conversion_factors=cf,
                env=env,
                max_pallets=cfg.get("max_pallets"),
                dispatch_interval=cfg.get("dispatch_interval", 1.0),
                dispatch_max_pallets=cfg.get("dispatch_max_pallets", 1),
            )
            nodes[node_name] = node

    # -- Pass 2: production nodes -------------------------------------------
    for node_name, cfg in config.NODES.items():
        if cfg["type"] == "production":
            node = ProductionNode(
                name=node_name,
                bom=cfg["bom"],
                output_conversion_factors=cfg.get("conversion_factors", {}),
                upstream_node=nodes[cfg["upstream"]],
                downstream_node=nodes[cfg["downstream"]],
                env=env,
                global_time_step=cfg.get("global_time_step", 10.0),
            )
            nodes[node_name] = node

    return nodes


def build_edges(config, nodes: dict[str, Any]) -> list[Edge]:
    edges = []
    for ecfg in config.EDGES:
        from_node = nodes[ecfg["from_node"]]
        to_node = nodes[ecfg["to_node"]]
        edge = Edge(
            from_node=from_node,
            to_node=to_node,
            transfer_mode=ecfg["transfer_mode"],
            transfer_time=ecfg["transfer_time"],
            batch_size=ecfg.get("batch_size", 1),
        )
        from_node.add_edge_out(edge)
        to_node.add_edge_in(edge)
        edges.append(edge)
    return edges


# ---------------------------------------------------------------------------
# Log printers
# ---------------------------------------------------------------------------

def print_state_snapshot(t: float, nodes: dict[str, Any]) -> None:
    """Prints a brief capacity snapshot at the given time."""
    print(f"  --- SNAPSHOT t={t} ---")
    for name, node in nodes.items():
        if hasattr(node, 'role') and node.role == NodeRole.WAREHOUSE:
            pal = node.current_pallets()
            print(f"    {name}: {pal} pallets / {node.node_max_pallets} used")
    print("  ---")


def process_events(
    job_manager: JobManager,
    nodes: dict[str, Any],
):
    events = job_manager.issue_pending_jobs(nodes)
    for ev in events:
        print(f"  [t={ev['time']:.1f}] JOB ISSUED: {ev['from']} -> {ev['to']}:")
        for sku, qty, pri in ev["orders"]:
            print(f"    -> Order: {sku} x{qty} (priority={pri})")


def process_all_logs(since_t, up_to_t, nodes, seen):
    all_new = []
    for name, node in nodes.items():
        if not hasattr(node, 'log'):
            continue
        for i, l in enumerate(node.log):
            if since_t <= l["time"] <= up_to_t + 1e-9:
                key = (name, i)
                if key not in seen:
                    seen.add(key)
                    all_new.append((name, l))
    all_new.sort(key=lambda x: x[1]["time"])
    for name, entry in all_new:
        t = entry["time"]
        if entry["type"] == "order_added":
            dest_str = (
                f" -> {entry.get('destination', '?')}"
                if entry.get("destination")
                else ""
            )
            print(
                f"  [t={t:.1f}] {name}: order queued"
                f" -> {entry['sku']} x{entry['quantity']}"
                f" (pri={entry['priority']}){dest_str}"
            )
        elif entry["type"] == "dispatched":
            dest_str = (
                f" -> {entry.get('destination', '?')}"
                if entry.get("destination")
                else ""
            )
            items_str = ", ".join(f"{sku}x{qty}" for sku, qty in entry["items"])
            print(f"  [t={t:.1f}] {name}: dispatched{dest_str} -> {items_str}")
        elif entry["type"] == "received":
            print(
                f"  [t={t:.1f}] {name}: received"
                f" {entry['sku']} x{entry['quantity']}"
                f" from {entry['source']}"
            )
        # -- production events --
        elif entry["type"] == "materials_consumed":
            inputs_str = ", ".join(f"{sku}x{qty}" for sku, qty in entry["inputs"].items())
            print(f"  [t={t:.1f}] {name}: consumed {inputs_str} for job #{entry['job_id']}")
        elif entry["type"] == "production_started":
            print(f"  [t={t:.1f}] {name}: production started job #{entry['job_id']}"
                  f" -> {entry['output_sku']} x{entry['quantity']}")
        elif entry["type"] == "production_output":
            print(f"  [t={t:.1f}] {name}: produced {entry['output_sku']} x{entry['quantity']}"
                  f" -> {entry.get('destination', '?')}")
        elif entry["type"] == "production_output_lost":
            print(f"  [t={t:.1f}] {name}: ** OUTPUT LOST **"
                  f" {entry['output_sku']} x{entry['quantity']}"
                  f" (downstream full)")
        elif entry["type"] == "production_completed":
            print(f"  [t={t:.1f}] {name}: production completed job #{entry['job_id']}"
                  f" -> {entry['output_sku']} x{entry['quantity']}")
        elif entry["type"] == "production_failed":
            print(f"  [t={t:.1f}] {name}: ** PRODUCTION FAILED ** job #{entry['job_id']}"
                  f" -> {entry['output_sku']} (insufficient material)")


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def run_scenario(scenario_name: str) -> SimulationResult:
    config = importlib.import_module(f"{scenario_name}.config")
    jobs_module = importlib.import_module(f"{scenario_name}.config_static_jobs")

    sim.yieldless(False)
    env = sim.Environment(trace=False)

    nodes = build_nodes(config, env)
    edges = build_edges(config, nodes)

    # -- load production orders into production nodes -----------------------
    if hasattr(jobs_module, 'PRODUCTION_JOBS'):
        for pjob in jobs_module.PRODUCTION_JOBS:
            target = nodes.get(pjob.node_name)
            if target is not None and hasattr(target, 'add_production_order'):
                target.add_production_order(pjob)

    job_manager = JobManager(jobs_module.JOBS, env)

    # -- print setup -------------------------------------------------------
    print("=" * 70)
    print(f"SIMULATION: {scenario_name}")
    print("=" * 70)
    print(f"SKUs: {config.SKUS}")
    print(f"Pallet sizes: {config.PALLET_SIZE}")
    print()
    print("Nodes:")
    for name, cfg in config.NODES.items():
        extra = ""
        if cfg["type"] == "production":
            extra = f", upstream={cfg['upstream']}, downstream={cfg['downstream']}"
        print(f"  {name}: type={cfg['type']}{extra}")
    print()
    print("Edges:")
    for e in edges:
        print(
            f"  {e.name} | mode={e.transfer_mode.value},"
            f" time={e.transfer_time}, batch={e.batch_size}"
        )
    print()
    print("Jobs:")
    for j in jobs_module.JOBS:
        print(f"  t={j.time}: {j.from_node} -> {j.to_node}:"
              f" {[(o.sku, o.quantity) for o in j.orders]}")
    if hasattr(jobs_module, 'PRODUCTION_JOBS'):
        print("Production orders:")
        for pj in jobs_module.PRODUCTION_JOBS:
            print(f"  t={pj.start_time}: {pj.node_name}: {pj.output_sku} x{pj.quantity} (job #{pj.job_id})")
    print("=" * 70)
    print()

    # -- simulation loop ---------------------------------------------------
    seen = set()
    step = 1
    process_events(job_manager, nodes)
    last_t = 0
    while last_t < config.SIM_DURATION:
        next_t = min(last_t + step, config.SIM_DURATION)
        env.run(next_t)
        process_events(job_manager, nodes)
        process_all_logs(last_t, env.now(), nodes, seen)
        last_t = env.now()

        if last_t % 20 == 0:
            print_state_snapshot(last_t, nodes)

    # -- final report ------------------------------------------------------
    print("=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)
    for name, node in nodes.items():
        if hasattr(node, 'role'):
            if node.role == NodeRole.WAREHOUSE:
                print(f"  {name} final inventory: {node.inventory}")
            elif node.role == NodeRole.SINK:
                print(f"  {name} final received: {node.received}")
        elif isinstance(node, ProductionNode):
            print(f"  {name} (production): completed {len([e for e in node.log if e['type'] == 'production_completed'])} jobs")

    # -- build & return result for programmatic consumption ----------------
    return SimulationResult(
        scenario_name=scenario_name,
        nodes=nodes,
        config=config,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    scenario = sys.argv[1] if len(sys.argv) > 1 else "scenario1"
    run_scenario(scenario)
