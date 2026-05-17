"""Tier 2 — Scenario integration tests.

Run full scenarios and assert on final state (inventory, sink, totals).
"""

from main import SimulationResult


# ---------------------------------------------------------------------------
# test_scenario2
# ---------------------------------------------------------------------------

class TestScenario2:
    """Source -> Warehouse -> Sink, one SKU.

    Jobs:
      t=0:   Warehouse -> Sink:  SKU_X x100  (no stock yet — queued)
      t=10:  Source -> Warehouse: SKU_X x50   (supplies the warehouse)
      t=120: Source -> Warehouse: SKU_X x100

    Expected final state (from known-correct run):
      Warehouse inventory: {SKU_X: 50}
      Sink received:       {SKU_X: 100}
    """

    def test_warehouse_final_inventory(self, scenario2_result: SimulationResult):
        inv = scenario2_result.warehouse_inventories
        assert "Warehouse" in inv
        assert inv["Warehouse"] == {"SKU_X": 50}

    def test_sink_received(self, scenario2_result: SimulationResult):
        received = scenario2_result.sink_received
        assert "Sink" in received
        assert received["Sink"] == {"SKU_X": 100}

    def test_warehouse_not_empty(self, scenario2_result: SimulationResult):
        """Verify we don't ship everything — 50 units remain in WH."""
        inv = scenario2_result.warehouse_inventories["Warehouse"]
        assert inv["SKU_X"] == 50



