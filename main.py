"""Main simulation entry point.

Usage:
    python main.py              → runs scenario1
    python main.py scenario1    → runs scenario1
    python main.py scenario2_test → runs scenario2_test
"""

import importlib
import sys

import salabim as sim

from src.edge import Edge
from src.warehouse_node import WarehouseNode, NodeRole
from src.management import JobManager


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------

def build_nodes(config, env: sim.Environment) -> dict[str, WarehouseNode]:
    nodes = {}
    for node_name, cfg in config.NODES.items():
        cf = dict(config.PALLET_SIZE)
        node = WarehouseNode(
            name=node_name,
            role=NodeRole(cfg["type"]),
            conversion_factors=cf,
            env=env,
            max_pallets=cfg.get("max_pallets"),
            dispatch_interval=cfg.get("dispatch_interval", 1.0),
            dispatch_max_pallets=cfg.get("dispatch_max_pallets", 1),
        )
        nodes[node_name] = node
    return nodes


def build_edges(config, nodes: dict[str, WarehouseNode]) -> list[Edge]:
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

def print_state_snapshot(t: float, nodes: dict[str, WarehouseNode]):
    """Prints a brief capacity snapshot at the given time."""
    print(f"  --- SNAPSHOT t={t} ---")
    for name, node in nodes.items():
        if node.role == NodeRole.WAREHOUSE:
            pal = node.current_pallets()
            print(f"    {name}: {pal} pallets / {node.node_max_pallets} used")
    print("  ---")


def process_events(
    job_manager: JobManager,
    nodes: dict[str, WarehouseNode],
):
    events = job_manager.issue_pending_jobs(nodes)
    for ev in events:
        print(f"  [t={ev['time']:.1f}] JOB ISSUED: {ev['from']} -> {ev['to']}:")
        for sku, qty, pri in ev["orders"]:
            print(f"    -> Order: {sku} x{qty} (priority={pri})")


def process_all_logs(since_t, up_to_t, nodes, seen):
    all_new = []
    for name, node in nodes.items():
        for i, l in enumerate(node.log):
            if since_t <= l["time"] <= up_to_t + 1e-9:
                key = (name, i)
                if key not in seen:
                    seen.add(key)
                    all_new.append((name, l))
    all_new.sort(key=lambda x: x[1]["time"])
    for name, entry in all_new:
        if entry["type"] == "order_added":
            dest_str = (
                f" -> {entry.get('destination', '?')}"
                if entry.get("destination")
                else ""
            )
            print(
                f"  [t={entry['time']:.1f}] {name}: order queued"
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
            print(f"  [t={entry['time']:.1f}] {name}: dispatched{dest_str} -> {items_str}")
        elif entry["type"] == "received":
            print(
                f"  [t={entry['time']:.1f}] {name}: received"
                f" {entry['sku']} x{entry['quantity']}"
                f" from {entry['source']}"
            )


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def run_scenario(scenario_name: str):
    config = importlib.import_module(f"{scenario_name}.config")
    jobs_module = importlib.import_module(f"{scenario_name}.config_static_jobs")

    sim.yieldless(False)
    env = sim.Environment(trace=False)

    nodes = build_nodes(config, env)
    edges = build_edges(config, nodes)
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
        print(f"  {name}: type={cfg['type']}, max_pallets={cfg.get('max_pallets', 'inf')}")
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
        print(f"  t={j.time}: {j.from_node} -> {j.to_node}: {[(o.sku, o.quantity) for o in j.orders]}")
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
        if node.role == NodeRole.WAREHOUSE:
            print(f"  {name} final inventory: {node.inventory}")
        elif node.role == NodeRole.SINK:
            print(f"  {name} final inventory: {node.received}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    scenario = sys.argv[1] if len(sys.argv) > 1 else "scenario1"
    run_scenario(scenario)
