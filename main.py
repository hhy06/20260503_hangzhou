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
import time

import salabim as sim

from src.infrastructure.edge import Edge
from src.infrastructure.warehouse_node import NodeRole
from src.infrastructure.production_node import ProductionNode
from src.builder import SimulationContext
from src.output import write_output


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
                logs.append({"node": str(edge), **entry})
        logs.sort(key=lambda x: x["time"])
        return logs


# ---------------------------------------------------------------------------
# Log printers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------


def run_scenario(scenario_name: str) -> SimulationResult:
    # Each scenario exposes a ``scenario_builder`` module with a
    # ``create_simulation()`` that returns a fully initialised context.
    builder = importlib.import_module(f"{scenario_name}.scenario_builder")
    ctx: SimulationContext = builder.create_simulation()

    orders_module = importlib.import_module(f"{scenario_name}.config_static_jobs")
    demand_module = importlib.import_module(f"{scenario_name}.demand")

    config = ctx.config
    env = ctx.env
    nodes = ctx.nodes
    edges = ctx.edges
    sku_map = ctx.sku_map

    # -- resolve management type for display gating -------------------------
    mgmt_cfg = getattr(config, "MANAGEMENT", {})
    mgmt_type = mgmt_cfg.get("type", "static_order")
    di = mgmt_cfg.get("decision_interval", 10.0)

    # -- print setup -------------------------------------------------------
    print("=" * 70)
    print(f"SIMULATION: {scenario_name}")
    print("=" * 70)
    # Handle both SKU objects and string mappings for SKUS display
    if hasattr(config, "SKUS_KEYS"):
        sku_items = [(sid, config.SKUS[sid].name if hasattr(config.SKUS.get(sid), "name") else sid) 
                     for sid in config.SKUS_KEYS]
    elif isinstance(config.SKUS, dict):
        first_val = next(iter(config.SKUS.values())) if config.SKUS else None
        if hasattr(first_val, "name"):
            sku_items = [(sid, sku.name) for sid, sku in config.SKUS.items()]
        else:
            sku_items = list(config.SKUS.items())
    else:
        sku_items = [(s, s) for s in config.SKUS]
    print("SKUs:")
    for sid, sname in sku_items[:10]:  # limit output
        print(f"  {sid}: {sname}")
    if len(sku_items) > 10:
        print(f"  ... +{len(sku_items) - 10} more")
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
            f"  {e} | mode={e.transfer_mode.value},"
            f" batch_transport_time={e.batch_transport_time}, batch_pallets={e.batch_pallets}"
        )
    print()
    if mgmt_type == "static_order":
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
                    f"  t={pj.activate_time}: {ndn}: {output_name} x{pj.quantity} (order #{pj.order_id})"
                )
    print("=" * 70)
    print()

    # -- simulation run ---------------------------------------------------
    # Run the simulation once to the configured duration.  The original code
    # called ``env.run(next_t)``, which interprets the argument as a
    # *duration* (not a *till* time), causing simulated time to overshoot
    # ``SIM_DURATION`` by a growing geometric progression (2^n−1).
    # Using ``env.run(till=...)`` fixes the semantics so the simulation
    # stops exactly at the configured duration.
    t0 = time.time()
    env.run(till=config.SIM_DURATION)
    t1 = time.time()
    

    print("=" * 70)
    print("SIMULATION COMPLETE")
    print(f"\nWall clock: start={t0:.3f}s  end={t1:.3f}s  elapsed={t1-t0:.3f}s")
    print("=" * 70)

    # -- final report -------------------------------------

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

    # -- demand fulfillment report -----------------------------------------
    if hasattr(demand_module, "DEMAND_ORDERS") and demand_module.DEMAND_ORDERS:
        _demand_total: dict[str, int] = {}
        for d in demand_module.DEMAND_ORDERS:
            s = d["sku"]
            _demand_total[s] = _demand_total.get(s, 0) + d["quantity"]

        _sink_received: dict[str, int] = {}
        for name, node in nodes.items():
            if hasattr(node, "role") and node.role == NodeRole.SINK:
                for sku, qty in node.received.items():
                    _sink_received[sku] = _sink_received.get(sku, 0) + qty

        print()
        print("  --- DEMAND FULFILLMENT ---")
        print(f"  {'SKU':<20} {'Ordered':>10} {'Received':>10} {'Met?':>8}")
        print(f"  {'-'*48}")
        all_met = True
        for sku in sorted(set(list(_demand_total.keys()) + list(_sink_received.keys()))):
            ordered = _demand_total.get(sku, 0)
            received = _sink_received.get(sku, 0)
            met = received >= ordered
            if not met:
                all_met = False
            print(f"  {_sku_display(sku, sku_map):<20} {ordered:>10} {received:>10} {'✓' if met else '✗':>8}")
        print(f"  {'-'*48}")
        print(f"  {'All demands met' if all_met else 'Some demands unmet':>48}")

    # -- write unified output -----------------------------------------------
    run_dir = write_output(
        scenario_name=scenario_name,
        nodes=nodes,
        edges=edges,
        management=ctx.management,
        sim_duration=config.SIM_DURATION,
        management_type=mgmt_type,
        decision_interval=di,
    )
    print(f"\nUnified output written to: {run_dir}")

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
    scenario = sys.argv[1] if len(sys.argv) > 1 else "scenario.ss_hangzhou0b"
    run_scenario(scenario)
