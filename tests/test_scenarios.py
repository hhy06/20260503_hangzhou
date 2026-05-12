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


# ---------------------------------------------------------------------------
# scenario1
# ---------------------------------------------------------------------------

class TestScenario1:
    """Source -> WarehouseA -> WarehouseB -> Sink, three SKUs.

    Jobs (total):
      SKU_A: 500+300+200 = 1000
      SKU_B: 200+100     = 300
      SKU_C: 1000+500    = 1500

    Path is Source→WA→WB→Sink with capacity constraints, but given enough
    time (SIM_DURATION=200) everything should eventually reach Sink.
    """

    def test_all_goods_eventually_reach_sink(self, scenario1_result: SimulationResult):
        received = scenario1_result.sink_received["Sink"]
        # Total ordered quantities
        assert received.get("SKU_A", 0) == 1000
        assert received.get("SKU_B", 0) == 300
        assert received.get("SKU_C", 0) == 1500

    def test_intermediate_warehouses_empty(self, scenario1_result: SimulationResult):
        """With sufficient time, all goods flow through to Sink."""
        inv = scenario1_result.warehouse_inventories
        for wh_name, wh_inv in inv.items():
            assert wh_inv == {}, f"{wh_name} should be empty but has {wh_inv}"

    def test_sink_total_matches_job_total(self, scenario1_result: SimulationResult):
        received = scenario1_result.sink_received["Sink"]
        total_items = sum(received.values())
        assert total_items == 1000 + 300 + 1500  # 2800
