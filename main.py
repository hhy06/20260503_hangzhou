"""Main simulation entry point.

Usage:
    python main.py                 → runs scenario1
    python main.py scenario1       → runs scenario1
    python main.py scenario.hangzhou0 → runs the Hangzhou scenario
"""

import importlib
from dataclasses import dataclass
from typing import Any
import sys

import salabim as sim

from src.infrastructure.edge import Edge
from src.infrastructure.warehouse_node import NodeRole
from src.infrastructure.production_node import ProductionNode
from src.builder import SimulationContext


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
    edges: list[Edge]
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
        """All log entries from all nodes and edges, sorted by simulation time."""
        logs: list[dict] = []
        for name, node in self.nodes.items():
            if hasattr(node, "log"):
                for entry in node.log:
                    logs.append({"node": name, **entry})
        for edge in self.edges:
            for entry in edge.log:
                logs.append({"node": edge.name, **entry})
        logs.sort(key=lambda x: x["time"])
        return logs


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
    edges: list[Edge] | None = None,
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
    if edges:
        for edge in edges:
            for i, l in enumerate(edge.log):
                if since_t <= l["time"] <= up_to_t + 1e-9:
                    key = (edge.name, i)
                    if key not in seen:
                        seen.add(key)
                        all_new.append((edge, l))
    all_new.sort(key=lambda x: x[1]["time"])
    for ent, entry in all_new:
        ndn = _dn(ent)
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
            sku_name = _sku_display(entry["sku"], sku_map) if sku_map else entry["sku"]
            print(
                f"  [t={t:.1f}] {ndn}: production started job #{entry['job_id']}"
                f" -> {sku_name} x{entry['quantity']}"
            )
        elif entry["type"] == "production_output":
            sku_name = _sku_display(entry["sku"], sku_map) if sku_map else entry["sku"]
            print(
                f"  [t={t:.1f}] {ndn}: produced {sku_name} x{entry['quantity']}"
                f" -> {entry.get('destination', '?')}"
            )
        elif entry["type"] == "production_completed":
            sku_name = _sku_display(entry["sku"], sku_map) if sku_map else entry["sku"]
            print(
                f"  [t={t:.1f}] {ndn}: production completed job #{entry['job_id']}"
                f" -> {sku_name} x{entry['quantity']}"
            )
        elif entry["type"] == "production_failed":
            sku_name = _sku_display(entry["sku"], sku_map) if sku_map else entry["sku"]
            print(
                f"  [t={t:.1f}] {ndn}: ** PRODUCTION FAILED ** job #{entry['job_id']}"
                f" -> {sku_name} (insufficient material)"
            )
        # -- transport events --
        elif entry["type"] == "transport_order_added":
            sku_name = _sku_display(entry["sku"], sku_map) if sku_map else entry["sku"]
            print(
                f"  [t={t:.1f}] {ndn}: transport order queued"
                f" {sku_name} x{entry['quantity']}"
                f" {entry['from']} -> {entry['to']}"
                f" (start={entry['start_time']}, expect={entry['expect_time']})"
            )
        elif entry["type"] == "transport_started":
            sku_name = _sku_display(entry["sku"], sku_map) if sku_map else entry["sku"]
            print(
                f"  [t={t:.1f}] {ndn}: transport started"
                f" {sku_name} x{entry['quantity']}"
                f" {entry['from']} -> {entry['to']}"
                f" ({entry['pallets']} pallets)"
            )
        elif entry["type"] == "transport_completed":
            sku_name = _sku_display(entry["sku"], sku_map) if sku_map else entry["sku"]
            print(
                f"  [t={t:.1f}] {ndn}: transport completed"
                f" {sku_name} x{entry['quantity']}"
                f" {entry['from']} -> {entry['to']}"
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
    # Each scenario exposes a ``scenario_builder`` module with a
    # ``create_simulation()`` that returns a fully initialised context.
    builder = importlib.import_module(f"{scenario_name}.scenario_builder")
    ctx: SimulationContext = builder.create_simulation()

    orders_module = importlib.import_module(f"{scenario_name}.config_static_jobs")

    config = ctx.config
    env = ctx.env
    nodes = ctx.nodes
    edges = ctx.edges
    sku_map = ctx.sku_map

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
            f" batch_transport_time={e.batch_transport_time}, batch_pallets={e.batch_pallets}"
        )
    print()
    print("Transport orders:")
    if hasattr(orders_module, "TRANSPORT_ORDERS"):
        for o in orders_module.TRANSPORT_ORDERS:
            sku_name = _sku_display(o.sku, sku_map)
            print(
                f"  t={o.start_time}: {o.from_node} -> {o.to_node}:"
                f" {sku_name} x{o.quantity}"
                f" (expect={o.expect_time})"
            )
    if hasattr(orders_module, "PRODUCTION_JOBS"):
        print("Production orders:")
        for pj in orders_module.PRODUCTION_JOBS:
            target_node = nodes.get(pj.node_name)
            ndn = _dn(target_node) if target_node else pj.node_name
            output_name = _sku_display(pj.sku, sku_map)
            print(
                f"  t={pj.activate_time}: {ndn}: {output_name} x{pj.quantity} (job #{pj.job_id})"
            )
    print("=" * 70)
    print()

    # -- simulation loop ---------------------------------------------------
    seen = set()
    step = 1
    last_t = 0
    while last_t < config.SIM_DURATION:
        next_t = min(last_t + step, config.SIM_DURATION)
        env.run(next_t)
        process_all_logs(last_t, env.now(), nodes, seen, sku_map, edges=edges)
        last_t = env.now()

        if last_t % 20 == 0:
            print_state_snapshot(last_t, nodes)

    # -- final report ------------------------------------------------------
    print("=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)
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
        edges=edges,
        config=config,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    scenario = sys.argv[1] if len(sys.argv) > 1 else "scenario.hangzhou0"
    run_scenario(scenario)
