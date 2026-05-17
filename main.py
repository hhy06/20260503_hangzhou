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

from collections import defaultdict

from src.edge import Edge
from src.warehouse_node import WarehouseNode, NodeRole
from src.management import JobManager, DECISION_INTERVAL
from src.production_node import ProductionNode


def _dn(node: object) -> str:
    """Return display name for a node object, falling back to str()."""
    if hasattr(node, "display_name"):
        return node.display_name
    return str(node)


def _sku_display(sku_id: str, sku_map: dict[str, str]) -> str:
    """Translate a SKU ID to its human-readable display name."""
    return sku_map.get(sku_id, sku_id)


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
            if hasattr(node, "role") and node.role == NodeRole.WAREHOUSE
        }

    @property
    def sink_received(self) -> dict[str, dict[str, int]]:
        return {
            name: dict(node.received)
            for name, node in self.nodes.items()
            if hasattr(node, "role") and node.role == NodeRole.SINK
        }

    @property
    def all_logs(self) -> list[dict]:
        """All log entries from all nodes, sorted by simulation time."""
        logs: list[dict] = []
        for name, node in self.nodes.items():
            if hasattr(node, "log"):
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
                display_name=cfg.get("display_name", node_name),
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
                display_name=cfg.get("display_name", node_name),
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
        if hasattr(node, "role") and node.role == NodeRole.WAREHOUSE:
            pal = node.current_pallets()
            print(f"    {_dn(node)}: {pal} pallets / {node.node_max_pallets} used")
    print("  ---")


def _lookup_display(nodes: dict[str, Any], internal_name: str) -> str:
    """Translate an internal node name to its display name via nodes dict."""
    node = nodes.get(internal_name)
    return _dn(node) if node else internal_name


def process_all_logs(
    since_t,
    up_to_t,
    nodes,
    seen,
    sku_map: dict[str, str] | None = None,
    job_manager: JobManager | None = None,
):
    all_new = []
    for name, node in nodes.items():
        if not hasattr(node, "log"):
            continue
        for i, l in enumerate(node.log):
            if since_t <= l["time"] <= up_to_t + 1e-9:
                key = (node.node_name, i)
                if key not in seen:
                    seen.add(key)
                    all_new.append((node, l))
    if job_manager is not None:
        for i, l in enumerate(job_manager.log):
            if since_t <= l["time"] <= up_to_t + 1e-9:
                key = ("__job_manager__", i)
                if key not in seen:
                    seen.add(key)
                    all_new.append((job_manager, l))
    all_new.sort(key=lambda x: x[1]["time"])
    for node, entry in all_new:
        ndn = _dn(node)
        t = entry["time"]
        if entry["type"] == "order_added":
            dest_raw = entry.get("destination")
            dest_str = f" -> {_lookup_display(nodes, dest_raw)}" if dest_raw else ""
            sku_name = _sku_display(entry["sku"], sku_map) if sku_map else entry["sku"]
            print(
                f"  [t={t:.1f}] {ndn}: order queued"
                f" -> {sku_name} x{entry['quantity']}"
                f" (pri={entry['priority']}){dest_str}"
            )
        elif entry["type"] == "dispatched":
            dest_raw = entry.get("destination")
            dest_str = f" -> {_lookup_display(nodes, dest_raw)}" if dest_raw else ""
            items_parts = []
            for sku, qty in entry["items"]:
                sku_name = _sku_display(sku, sku_map) if sku_map else sku
                items_parts.append(f"{sku_name}x{qty}")
            items_str = ", ".join(items_parts)
            print(f"  [t={t:.1f}] {ndn}: dispatched{dest_str} -> {items_str}")
        elif entry["type"] == "received":
            sku_name = _sku_display(entry["sku"], sku_map) if sku_map else entry["sku"]
            print(
                f"  [t={t:.1f}] {ndn}: received"
                f" {sku_name} x{entry['quantity']}"
                f" from {entry['source']}"
            )
        # -- production events --
        elif entry["type"] == "materials_consumed":
            inputs_parts = []
            for sku, qty in entry["inputs"].items():
                sku_name = _sku_display(sku, sku_map) if sku_map else sku
                inputs_parts.append(f"{sku_name}x{qty}")
            inputs_str = ", ".join(inputs_parts)
            print(
                f"  [t={t:.1f}] {ndn}: consumed {inputs_str} for job #{entry['job_id']}"
            )
        elif entry["type"] == "production_started":
            sku_name = _sku_display(entry["output_sku"], sku_map) if sku_map else entry["output_sku"]
            print(
                f"  [t={t:.1f}] {ndn}: production started job #{entry['job_id']}"
                f" -> {sku_name} x{entry['quantity']}"
            )
        elif entry["type"] == "production_output":
            sku_name = _sku_display(entry["output_sku"], sku_map) if sku_map else entry["output_sku"]
            print(
                f"  [t={t:.1f}] {ndn}: produced {sku_name} x{entry['quantity']}"
                f" -> {entry.get('destination', '?')}"
            )
        elif entry["type"] == "production_output_lost":
            sku_name = _sku_display(entry["output_sku"], sku_map) if sku_map else entry["output_sku"]
            print(
                f"  [t={t:.1f}] {ndn}: ** OUTPUT LOST **"
                f" {sku_name} x{entry['quantity']}"
                f" (downstream full)"
            )
        elif entry["type"] == "production_completed":
            sku_name = _sku_display(entry["output_sku"], sku_map) if sku_map else entry["output_sku"]
            print(
                f"  [t={t:.1f}] {ndn}: production completed job #{entry['job_id']}"
                f" -> {sku_name} x{entry['quantity']}"
            )
        elif entry["type"] == "production_failed":
            sku_name = _sku_display(entry["output_sku"], sku_map) if sku_map else entry["output_sku"]
            print(
                f"  [t={t:.1f}] {ndn}: ** PRODUCTION FAILED ** job #{entry['job_id']}"
                f" -> {sku_name} (insufficient material)"
            )
        elif entry["type"] == "job_issued":
            from_dn = _lookup_display(nodes, entry["from"])
            to_dn = _lookup_display(nodes, entry["to"])
            print(f"  [t={t:.1f}] JOB ISSUED: {from_dn} -> {to_dn}:")
            for sku, qty, pri in entry["orders"]:
                sku_name = _sku_display(sku, sku_map) if sku_map else sku
                print(f"    -> Order: {sku_name} x{qty} (priority={pri})")


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
    if hasattr(jobs_module, "PRODUCTION_JOBS"):
        for pjob in jobs_module.PRODUCTION_JOBS:
            target = nodes.get(pjob.node_name)
            if target is not None and hasattr(target, "add_production_order"):
                target.add_production_order(pjob)

    sku_map: dict[str, str] = getattr(config, "SKUS", {})
    if isinstance(sku_map, (list, tuple)):
        # Legacy: SKUS is a list — build identity map for backward compat
        sku_map = {s: s for s in sku_map}

    demand_module = importlib.import_module(f"{scenario_name}.static_demand")
    demand = getattr(demand_module, "DEMAND", {})
    pallet_sizes = getattr(config, "PALLET_SIZE", {})
    job_manager = JobManager(
        jobs_module.JOBS, nodes, env, demand=demand, pallet_sizes=pallet_sizes,
        day_length=config.DAY, shift_starts=config.SHIFT_STARTS,
        shift_duration=config.SHIFT_DURATION,
    )

    # -- print setup -------------------------------------------------------
    print("=" * 70)
    print(f"SIMULATION: {scenario_name}")
    print("=" * 70)
    if isinstance(config.SKUS, dict):
        print("SKUs:")
        for sid, sname in config.SKUS.items():
            print(f"  {sid}: {sname}")
    else:
        print(f"SKUs: {config.SKUS}")
    print(f"Pallet sizes: {config.PALLET_SIZE}")
    print()
    print("Nodes:")
    for name, cfg in config.NODES.items():
        display = cfg.get("display_name", name)
        extra = ""
        if cfg["type"] == "production":
            extra = f", upstream={cfg['upstream']}, downstream={cfg['downstream']}"
        print(f"  {display} ({name}): type={cfg['type']}{extra}")
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
        orders_str = ", ".join(
            f"{_sku_display(o.sku, sku_map)} x{o.quantity}" for o in j.orders
        )
        print(
            f"  t={j.time}: {j.from_node} -> {j.to_node}:"
            f" [{orders_str}]"
        )
    if hasattr(jobs_module, "PRODUCTION_JOBS"):
        print("Production orders:")
        for pj in jobs_module.PRODUCTION_JOBS:
            target_node = nodes.get(pj.node_name)
            ndn = _dn(target_node) if target_node else pj.node_name
            output_name = _sku_display(pj.output_sku, sku_map)
            print(
                f"  t={pj.start_time}: {ndn}: {output_name} x{pj.quantity} (job #{pj.job_id})"
            )
    print("=" * 70)
    print()

    DAY = config.DAY
    sink_node = next(
        (n for n in nodes.values() if hasattr(n, "role") and n.role == NodeRole.SINK),
        None,
    )

    seen = set()
    step = DECISION_INTERVAL
    last_t = 0

    while last_t < config.SIM_DURATION:
        next_t = min(last_t + step, config.SIM_DURATION)
        env.run(next_t)
        process_all_logs(last_t, env.now(), nodes, seen, sku_map, job_manager=job_manager)
        last_t = env.now()

    print("=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)

    day_received: dict[int, dict[str, int]] = {}
    if sink_node is not None:
        for entry in sink_node.log:
            if entry["type"] == "received":
                day = int(entry["time"] // DAY) + 1
                if day not in day_received:
                    day_received[day] = {}
                day_received[day][entry["sku"]] = (
                    day_received[day].get(entry["sku"], 0) + entry["quantity"]
                )

    if demand:
        print("\nDay-by-Day FG Satisfaction Rate")
    all_fg_skus = sorted({sku for d in demand.values() for sku in d})
    col_width = 10
    for sku in all_fg_skus:
        print(f"{_sku_display(sku, sku_map):<{col_width}} ", end="")
    print()
    print(f"{'':-<6}-", end="")
    for _ in all_fg_skus:
        print(f"{'':-<{col_width + 1}}", end="")
    print()

    for day in sorted(demand):
        day_demand = demand[day]
        day_recv = day_received.get(day, {})
        print(f"{day:<6} ", end="")
        for sku in all_fg_skus:
            dem = day_demand.get(sku, 0)
            recv = day_recv.get(sku, 0)
            if dem > 0:
                label = f"{recv}/{dem}"
            else:
                label = f"{recv}/0"
            print(f"{label:>{col_width}} ", end="")
        print()
    print()

    for name, node in nodes.items():
        ndn = _dn(node)
        if hasattr(node, "role"):
            if node.role == NodeRole.WAREHOUSE:
                inv_display = {_sku_display(k, sku_map): v for k, v in node.inventory.items()}
                print(f"  {ndn} final inventory: {inv_display}")
            elif node.role == NodeRole.SINK:
                recv_display = {_sku_display(k, sku_map): v for k, v in node.received.items()}
                print(f"  {ndn} final received: {recv_display}")
        elif isinstance(node, ProductionNode):
            print(
                f"  {ndn} (production): completed {len([e for e in node.log if e['type'] == 'production_completed'])} jobs"
            )

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
