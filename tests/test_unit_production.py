"""Unit tests for ProductionNode — material consumption, timing, queue order."""

import math

import pytest
import salabim as sim

from src.warehouse_node import WarehouseNode, NodeRole
from src.production_node import ProductionNode, ProductionOrder


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _make_production_scene(**prod_overrides):
    """Create a minimal production scene with one ProductionNode.

    Returns
    -------
    env : sim.Environment
    upstream : WarehouseNode
    prod : ProductionNode
    downstream : WarehouseNode
    """
    env = sim.Environment(trace=False)

    upstream = WarehouseNode(
        name="Upstream",
        role=NodeRole.WAREHOUSE,
        conversion_factors={"wip_X": 100, "wip_Y": 100},
        env=env,
        max_pallets=1000,
        dispatch_interval=1,
        dispatch_max_pallets=999,
    )
    downstream = WarehouseNode(
        name="Downstream",
        role=NodeRole.WAREHOUSE,
        conversion_factors={"SKU_A": 50},
        env=env,
        max_pallets=500,
        dispatch_interval=1,
        dispatch_max_pallets=999,
    )

    bom = {
        "SKU_A": {
            "inputs": {"wip_X": 1, "wip_Y": 1},
            "speed": 10.0,
            "lead_time": 5.0,
        },
    }

    params = dict(
        name="TestProd",
        bom=bom,
        output_conversion_factors={"SKU_A": 50},
        upstream_node=upstream,
        downstream_node=downstream,
        env=env,
        global_time_step=10.0,
    )
    params.update(prod_overrides)
    prod = ProductionNode(**params)

    return env, upstream, prod, downstream


def _seed_upstream(upstream: WarehouseNode, sku: str, qty: int):
    """Set upstream warehouse inventory directly."""
    upstream.inventory[sku] = upstream.inventory.get(sku, 0) + qty


# ===========================================================================
# Material checks
# ===========================================================================

class TestCheckMaterials:
    def test_sufficient_materials(self):
        _, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 100)
        _seed_upstream(up, "wip_Y", 100)
        assert prod._check_materials({"wip_X": 50, "wip_Y": 50}) is True

    def test_insufficient_single_sku(self):
        _, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 10)
        _seed_upstream(up, "wip_Y", 100)
        assert prod._check_materials({"wip_X": 50, "wip_Y": 50}) is False

    def test_insufficient_both_skus(self):
        _, up, prod, _ = _make_production_scene()
        assert prod._check_materials({"wip_X": 1, "wip_Y": 1}) is False

    def test_exact_materials(self):
        _, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 50)
        _seed_upstream(up, "wip_Y", 50)
        assert prod._check_materials({"wip_X": 50, "wip_Y": 50}) is True

    def test_more_available_than_needed(self):
        _, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 500)
        _seed_upstream(up, "wip_Y", 500)
        assert prod._check_materials({"wip_X": 50, "wip_Y": 50}) is True


# ===========================================================================
# Material consumption
# ===========================================================================

class TestConsumeMaterials:
    def test_consumes_correct_quantities(self):
        _, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 100)
        _seed_upstream(up, "wip_Y", 100)
        prod._consume_materials({"wip_X": 30, "wip_Y": 40})
        assert up.inventory.get("wip_X", 0) == 70
        assert up.inventory.get("wip_Y", 0) == 60

    def test_consumes_all_and_removes_key(self):
        _, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 50)
        _seed_upstream(up, "wip_Y", 50)
        prod._consume_materials({"wip_X": 50, "wip_Y": 50})
        assert "wip_X" not in up.inventory
        assert "wip_Y" not in up.inventory

    def test_multiple_consumptions_stack(self):
        _, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 100)
        prod._consume_materials({"wip_X": 30})
        prod._consume_materials({"wip_X": 20})
        assert up.inventory["wip_X"] == 50


# ===========================================================================
# Queue ordering
# ===========================================================================

class TestProductionQueueOrder:
    def test_sort_by_start_time_then_job_id(self):
        _, _, prod, _ = _make_production_scene()
        prod.add_production_order(ProductionOrder(job_id=3, output_sku="A", quantity=10, start_time=10, node_name="X"))
        prod.add_production_order(ProductionOrder(job_id=1, output_sku="A", quantity=10, start_time=5, node_name="X"))
        prod.add_production_order(ProductionOrder(job_id=2, output_sku="A", quantity=10, start_time=10, node_name="X"))
        # Expected order: (5,1), (10,2), (10,3)
        assert [j.job_id for j in prod.production_queue] == [1, 2, 3]

    def test_same_start_time_lower_job_id_first(self):
        _, _, prod, _ = _make_production_scene()
        prod.add_production_order(ProductionOrder(job_id=5, output_sku="A", quantity=10, start_time=5, node_name="X"))
        prod.add_production_order(ProductionOrder(job_id=3, output_sku="A", quantity=10, start_time=5, node_name="X"))
        prod.add_production_order(ProductionOrder(job_id=4, output_sku="A", quantity=10, start_time=5, node_name="X"))
        assert prod.production_queue[0].job_id == 3
        assert prod.production_queue[1].job_id == 4
        assert prod.production_queue[2].job_id == 5


# ===========================================================================
# Output to downstream
# ===========================================================================

class TestOutputToDownstream:
    def test_successful_output(self):
        _, up, prod, down = _make_production_scene()
        # Make downstream has capacity
        ok = prod._output_to_downstream("SKU_A", 100)
        assert ok is True
        assert down.inventory.get("SKU_A", 0) == 100
        # Should have a production_output log entry
        assert any(e["type"] == "production_output" for e in prod.log)

    def test_output_lost_when_downstream_full(self):
        _, up, prod, down = _make_production_scene()
        # Fill downstream to capacity
        down.inventory["SKU_A"] = 500 * 50  # max_pallets=500, items=500*50
        ok = prod._output_to_downstream("SKU_A", 1)
        assert ok is False
        # Should have a production_output_lost log entry
        assert any(e["type"] == "production_output_lost" for e in prod.log)


# ===========================================================================
# Full job execution (timing verification)
# ===========================================================================

class TestExecuteJob:
    def test_production_fails_on_insufficient_material(self):
        env, up, prod, _ = _make_production_scene()
        # No materials in upstream
        job = ProductionOrder(job_id=1, output_sku="SKU_A", quantity=100, start_time=0, node_name="TestProd")
        prod.add_production_order(job)

        sim.yieldless(False)
        env.run(100)
        assert any(e["type"] == "production_failed" for e in prod.log)

    def test_job_not_started_before_start_time(self):
        env, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 500)
        _seed_upstream(up, "wip_Y", 500)

        job = ProductionOrder(job_id=1, output_sku="SKU_A", quantity=100, start_time=50, node_name="TestProd")
        prod.add_production_order(job)

        sim.yieldless(False)
        env.run(10)
        # At t=10, job should not have started
        assert not any(e["type"] == "production_started" for e in prod.log)

    def test_job_starts_at_start_time(self):
        env, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 500)
        _seed_upstream(up, "wip_Y", 500)

        job = ProductionOrder(job_id=1, output_sku="SKU_A", quantity=100, start_time=0, node_name="TestProd")
        prod.add_production_order(job)

        sim.yieldless(False)
        env.run(1)
        assert any(e["type"] == "production_started" for e in prod.log)

    def test_production_batch_timing(self):
        """250 units, speed=10/min, lead=5min, step=10min.

        Expected:
            t=0   consume
            t=5   lead done
            t=15  output 100 (batch 1)
            t=25  output 100 (batch 2)
            t=30  output 50  (batch 3, partial)

        Total job time from consume to completion: 30 min
        """
        env, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 500)
        _seed_upstream(up, "wip_Y", 500)

        job = ProductionOrder(job_id=1, output_sku="SKU_A", quantity=250, start_time=0, node_name="TestProd")
        prod.add_production_order(job)

        sim.yieldless(False)

        # Run to t=30 (production should complete just after t=30)
        env.run(35)

        output_events = [e for e in prod.log if e["type"] == "production_output"]
        assert len(output_events) == 3
        assert output_events[0]["quantity"] == 100   # batch 1
        assert output_events[1]["quantity"] == 100   # batch 2
        assert output_events[2]["quantity"] == 50    # batch 3

        completed = [e for e in prod.log if e["type"] == "production_completed"]
        assert len(completed) == 1
        assert completed[0]["quantity"] == 250

        # Verify downstream received all 250
        assert prod.downstream_node.inventory.get("SKU_A", 0) == 250

    def test_material_consumption_matches_bom(self):
        """250 SKU_A should consume 250 wip_X + 250 wip_Y."""
        env, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 500)
        _seed_upstream(up, "wip_Y", 500)

        job = ProductionOrder(job_id=1, output_sku="SKU_A", quantity=250, start_time=0, node_name="TestProd")
        prod.add_production_order(job)

        sim.yieldless(False)
        env.run(100)

        # 500 - 250 = 250 remaining
        assert up.inventory.get("wip_X", 0) == 250
        assert up.inventory.get("wip_Y", 0) == 250

    def test_two_jobs_sequential(self):
        """Job 1 (250 units, t=0) then Job 2 (100 units, t=50)."""
        env, up, prod, _ = _make_production_scene()
        _seed_upstream(up, "wip_X", 1000)
        _seed_upstream(up, "wip_Y", 1000)

        prod.add_production_order(
            ProductionOrder(job_id=1, output_sku="SKU_A", quantity=250, start_time=0, node_name="TestProd"))
        prod.add_production_order(
            ProductionOrder(job_id=2, output_sku="SKU_A", quantity=100, start_time=50, node_name="TestProd"))

        sim.yieldless(False)
        env.run(200)

        completed = [e for e in prod.log if e["type"] == "production_completed"]
        assert len(completed) == 2

        downstream_total = prod.downstream_node.inventory.get("SKU_A", 0)
        assert downstream_total == 350  # 250 + 100
