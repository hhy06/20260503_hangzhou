"""Shared fixtures and invariant helpers for warehouse simulation tests."""

from collections.abc import Generator
from typing import Any

import pytest
import salabim as sim

from main import SimulationResult
from src.infrastructure.warehouse_node import NodeRole
from src.infrastructure.edge import Edge


# ---------------------------------------------------------------------------
# salabim environment for unit tests (function-scoped)
# ---------------------------------------------------------------------------

@pytest.fixture
def env() -> Generator[sim.Environment, None, None]:
    _env = sim.Environment(trace=False)
    yield _env


# ---------------------------------------------------------------------------
# Invariant check helpers
# ---------------------------------------------------------------------------

InventoryTrajectory = list[dict[str, Any]]
"""Each entry: {time, event_type, sku, delta, inventory_snapshot, pallets_used}"""


def compute_warehouse_trajectory(
    result: SimulationResult, node_name: str,
) -> InventoryTrajectory:
    """Replay receive log events for a warehouse to track inventory over time."""
    node = result.nodes[node_name]
    if node.role != NodeRole.WAREHOUSE:
        raise ValueError(f"{node_name} is not a Warehouse node")

    inventory: dict[str, int] = {}
    trajectory: InventoryTrajectory = []

    for entry in sorted(node.log, key=lambda e: e["time"]):
        if entry["type"] == "received":
            sku: str = entry["sku"]
            qty: int = entry["quantity"]
            inventory[sku] = inventory.get(sku, 0) + qty
            total_pallets = sum(
                node.pallets_for_quantity(s, q) for s, q in inventory.items()
            )
            trajectory.append({
                "time": entry["time"],
                "event_type": "receive",
                "sku": sku,
                "delta": qty,
                "inventory_snapshot": dict(inventory),
                "pallets_used": total_pallets,
            })

    return trajectory


def _source_outflow(result: SimulationResult) -> dict[str, int]:
    """Total items that left source nodes (via edge transport_started)."""
    out: dict[str, int] = {}
    for edge in result.edges:
        for entry in edge.log:
            if entry["type"] == "transport_started":
                from_name = entry["from"]
                node = result.nodes.get(from_name)
                if node is not None and hasattr(node, "role") and node.role == NodeRole.SOURCE:
                    sku = entry["sku"]
                    qty = entry["quantity"]
                    out[sku] = out.get(sku, 0) + qty
    return out


def _sink_inflow(result: SimulationResult) -> dict[str, int]:
    """Total items received by sink nodes."""
    sink_in: dict[str, int] = {}
    for name, node in result.nodes.items():
        if node.role == NodeRole.SINK:
            for entry in node.log:
                if entry["type"] == "received":
                    sku = entry["sku"]
                    qty = entry["quantity"]
                    sink_in[sku] = sink_in.get(sku, 0) + qty
    return sink_in


def check_conservation(result: SimulationResult) -> list[str]:
    """Verify goods conservation: source outflow = sink inflow + Δ warehouse.

    Source outflow is measured from edge ``transport_started`` events where
    the source node has role SOURCE.
    """
    source_out = _source_outflow(result)
    sink_in = _sink_inflow(result)

    # Sum final warehouse inventory across all warehouses
    wh_final: dict[str, int] = {}
    for name, node in result.nodes.items():
        if node.role == NodeRole.WAREHOUSE:
            for sku, qty in node.inventory.items():
                wh_final[sku] = wh_final.get(sku, 0) + qty

    errors: list[str] = []
    all_skus = set(source_out.keys()) | set(sink_in.keys()) | set(wh_final.keys())
    for sku in sorted(all_skus):
        sourced = source_out.get(sku, 0)
        sunk = sink_in.get(sku, 0)
        in_wh = wh_final.get(sku, 0)
        if sourced != sunk + in_wh:
            errors.append(
                f"SKU {sku}: sourced={sourced}, sunk={sunk}, "
                f"warehouse={in_wh} (delta={sourced - sunk - in_wh})"
            )
    return errors


def check_capacity_constraints(result: SimulationResult) -> list[str]:
    """Verify no warehouse ever exceeds its max_pallets.

    NOTE: With the soft-cap design this invariant is informational —
    exceeding capacity triggers a warning but does not fail.
    """
    errors: list[str] = []
    for name, node in result.nodes.items():
        if node.role != NodeRole.WAREHOUSE:
            continue
        trajectory = compute_warehouse_trajectory(result, name)
        max_pal = node.node_max_pallets
        if max_pal is None:
            continue
        for event in trajectory:
            if event["pallets_used"] > max_pal:
                errors.append(
                    f"{name} @ t={event['time']}: {event['pallets_used']} pallets "
                    f"used (max={max_pal}) — event: {event['event_type']} "
                    f"{event['sku']} ({event['delta']:+d})"
                )
    return errors
