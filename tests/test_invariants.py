"""Tier 3 — Property-based invariant tests.

These tests verify cross-cutting correctness properties that must hold
for *any* valid scenario configuration.

Invariants:
  1. Conservation of goods — goods are neither created nor destroyed
  2. Capacity not exceeded — warehouses never exceed max_pallets
  3. No negative inventory — dispatches never exceed available stock
"""

from main import SimulationResult
from tests.conftest import (
    check_conservation,
    check_capacity_constraints,
    check_no_negative_inventory,
)


# ---------------------------------------------------------------------------
# Invariant ① — Conservation of goods
# ---------------------------------------------------------------------------

class TestConservationOfGoods:
    """Sum(source dispatches) = sum(sink receives) + Δ(warehouse inventory)"""

    def test_scenario2(self, scenario2_result: SimulationResult):
        errors = check_conservation(scenario2_result)
        assert not errors, "\n".join(errors)

# ---------------------------------------------------------------------------
# Invariant ② — Capacity never exceeded
# ---------------------------------------------------------------------------

class TestCapacityConstraints:
    """∀ warehouse, ∀ t: pallets_used(t) ≤ max_pallets"""

    def test_scenario2(self, scenario2_result: SimulationResult):
        errors = check_capacity_constraints(scenario2_result)
        assert not errors, "\n".join(errors)



# ---------------------------------------------------------------------------
# Invariant ③ — No negative inventory
# ---------------------------------------------------------------------------

class TestNoNegativeInventory:
    """∀ warehouse dispatch: quantity ≤ current stock"""

    def test_scenario2(self, scenario2_result: SimulationResult):
        errors = check_no_negative_inventory(scenario2_result)
        assert not errors, "\n".join(errors)


