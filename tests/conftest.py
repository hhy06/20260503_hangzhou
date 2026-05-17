"""Shared fixtures and invariant helpers for warehouse simulation tests."""

from collections.abc import Generator
from typing import Any

import pytest
import salabim as sim

from main import run_scenario, SimulationResult
from src.warehouse_node import NodeRole


# ---------------------------------------------------------------------------
# Fixtures — run each scenario once per session (results are read-only)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def scenario2_result() -> SimulationResult:
    return run_scenario("test_scenario2")


# ---------------------------------------------------------------------------
# salabim environment for unit tests (cheap, function-scoped)
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
    """Replay log events for a warehouse to track inventory over time.

    Returns a list of events in chronological order, each with a snapshot
    of inventory *after* the event was applied.
    """
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
            pallets = node.pallets_for_quantity(sku, inventory.get(sku, 0))
            # recompute total pallets across all SKUs
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

        elif entry["type"] == "dispatched":
            for sku, qty in entry["items"]:
                before = inventory.get(sku, 0)
                inventory[sku] = before - qty
                if inventory[sku] <= 0:
                    if inventory[sku] < 0:
                        # negative — will be flagged by invariant
                        pass
                    del inventory[sku]
                total_pallets = sum(
                    node.pallets_for_quantity(s, q) for s, q in inventory.items()
                )
                trajectory.append({
                    "time": entry["time"],
                    "event_type": "dispatch",
                    "sku": sku,
                    "delta": -qty,
                    "inventory_snapshot": dict(inventory),
                    "pallets_used": total_pallets,
                })

    return trajectory


def check_conservation(result: SimulationResult) -> list[str]:
    """Verify goods conservation: Source outflow = Sink inflow + Δ Warehouse.

    Returns a list of error messages (empty = all good).
    """
    source_out: dict[str, int] = {}
    sink_in: dict[str, int] = {}

    for name, node in result.nodes.items():
        for entry in node.log:
            if entry["type"] == "dispatched" and node.role == NodeRole.SOURCE:
                for sku, qty in entry["items"]:
                    source_out[sku] = source_out.get(sku, 0) + qty
            elif entry["type"] == "received" and node.role == NodeRole.SINK:
                sku = entry["sku"]
                qty = entry["quantity"]
                sink_in[sku] = sink_in.get(sku, 0) + qty

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

    Returns a list of error messages (empty = all good).
    """
    errors: list[str] = []
    for name, node in result.nodes.items():
        if node.role != NodeRole.WAREHOUSE:
            continue
        trajectory = compute_warehouse_trajectory(result, name)
        max_pal = node.node_max_pallets
        for event in trajectory:
            if event["pallets_used"] > max_pal:
                errors.append(
                    f"{name} @ t={event['time']}: {event['pallets_used']} pallets "
                    f"used (max={max_pal}) — event: {event['event_type']} "
                    f"{event['sku']} ({event['delta']:+d})"
                )
    return errors


def check_no_negative_inventory(result: SimulationResult) -> list[str]:
    """Verify no warehouse dispatch exceeds available stock.

    Returns a list of error messages (empty = all good).
    """
    errors: list[str] = []
    for name, node in result.nodes.items():
        if node.role != NodeRole.WAREHOUSE:
            continue

        inventory: dict[str, int] = {}
        for entry in sorted(node.log, key=lambda e: e["time"]):
            if entry["type"] == "received":
                sku = entry["sku"]
                inventory[sku] = inventory.get(sku, 0) + entry["quantity"]
            elif entry["type"] == "dispatched":
                for sku, qty in entry["items"]:
                    before = inventory.get(sku, 0)
                    after = before - qty
                    if after < 0:
                        errors.append(
                            f"{name} @ t={entry['time']}: dispatched {sku} x{qty} "
                            f"but only {before} in stock (shortfall={-after})"
                        )
                    inventory[sku] = after
                    if inventory[sku] <= 0:
                        del inventory[sku]
    return errors
