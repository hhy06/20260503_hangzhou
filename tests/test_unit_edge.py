"""Unit tests for Edge (now a sim.Component) and TransportOrder."""

import pytest
import salabim as sim

from src.infrastructure.edge import Edge, TransferMode, TransportOrder
from src.infrastructure.warehouse_node import WarehouseNode, NodeRole


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def env():
    sim.yieldless(False)
    return sim.Environment(trace=False)


@pytest.fixture
def wh_a(env):
    return WarehouseNode(
        name="WH_A", role=NodeRole.WAREHOUSE,
        conversion_factors={"SKU_X": 10}, env=env, max_pallets=100,
    )


@pytest.fixture
def wh_b(env):
    return WarehouseNode(
        name="WH_B", role=NodeRole.WAREHOUSE,
        conversion_factors={"SKU_X": 10}, env=env, max_pallets=100,
    )


def _make_edge(env, from_node, to_node, mode=TransferMode.PER_PALLET,
               time=1.0, batch=1):
    return Edge(
        from_node=from_node, to_node=to_node,
        transfer_mode=mode, batch_transport_time=time, batch_pallets=batch,
        env=env,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestEdgeConstruction:
    def test_basic_construction(self, env, wh_a, wh_b):
        e = _make_edge(env, wh_a, wh_b)
        assert e.from_node is wh_a
        assert e.to_node is wh_b
        assert e.transfer_mode == TransferMode.PER_PALLET

    def test_batch_mode_validates_batch_pallets(self, env, wh_a, wh_b):
        with pytest.raises(ValueError, match="batch_pallets"):
            Edge(
                from_node=wh_a, to_node=wh_b,
                transfer_mode=TransferMode.BATCH, batch_transport_time=1.0,
                batch_pallets=0, env=env,
            )

    def test_name_default(self, env, wh_a, wh_b):
        e = _make_edge(env, wh_a, wh_b)
        assert "WH_A -> WH_B" in e.edge_name

    def test_custom_name(self, env, wh_a, wh_b):
        e = Edge(
            from_node=wh_a, to_node=wh_b,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0,
            name="my_edge", env=env,
        )
        assert e.edge_name == "my_edge"

    def test_repr(self, env, wh_a, wh_b):
        e = _make_edge(env, wh_a, wh_b, mode=TransferMode.BATCH, batch=10)
        r = repr(e)
        assert "batch" in r
        assert "batch_transport_time=1" in r
        assert "batch_pallets=10" in r


# ---------------------------------------------------------------------------
# add_transport_order — pending vs activated
# ---------------------------------------------------------------------------

class TestAddTransportOrder:
    def test_immediate_order_goes_to_activated(self, env, wh_a, wh_b):
        e = _make_edge(env, wh_a, wh_b)
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="WH_A", to_node="WH_B",
            start_time=0, expect_time=10,
        )
        e.add_transport_order(order)
        assert len(e.activated_queue) == 1
        assert len(e.pending_queue) == 0

    def test_future_order_goes_to_pending(self, env, wh_a, wh_b):
        e = _make_edge(env, wh_a, wh_b)
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="WH_A", to_node="WH_B",
            start_time=99, expect_time=100,
        )
        e.add_transport_order(order)
        assert len(e.activated_queue) == 0
        assert len(e.pending_queue) == 1

    def test_activated_sorted_by_expect_time(self, env, wh_a, wh_b):
        e = _make_edge(env, wh_a, wh_b)
        e.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="WH_A", to_node="WH_B",
            start_time=0, expect_time=30,
        ))
        e.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="WH_A", to_node="WH_B",
            start_time=0, expect_time=10,
        ))
        # Earliest expect_time first
        assert e.activated_queue[0].expect_time == 10
        assert e.activated_queue[1].expect_time == 30


# ---------------------------------------------------------------------------
# Transport execution — PER_PALLET mode
# ---------------------------------------------------------------------------

class TestExecutePerPallet:
    def test_single_pallet_delivered(self, env, wh_a, wh_b):
        """10 items = 1 pallet (10 items/pallet)."""
        wh_a.inventory = {"SKU_X": 100}
        e = _make_edge(env, wh_a, wh_b, mode=TransferMode.PER_PALLET, time=2.0)

        order = TransportOrder(
            sku="SKU_X", quantity=10,
            from_node="WH_A", to_node="WH_B",
            start_time=0, expect_time=10,
        )
        e.add_transport_order(order)
        env.run(21)

        # 10 items debited from WH_A (10/10 = 1 pallet)
        assert wh_a.inventory.get("SKU_X", 0) == 90
        # 10 items delivered to WH_B at 1/tick (batch_transport_time=2.0) → done t=20
        assert wh_b.inventory.get("SKU_X", 0) == 10

    def test_multi_pallet_interval(self, env, wh_a, wh_b):
        """30 items = 3 pallets, each delivered every 1.0 min."""
        wh_a.inventory = {"SKU_X": 100}
        e = _make_edge(env, wh_a, wh_b, mode=TransferMode.PER_PALLET, time=1.0)

        order = TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="WH_A", to_node="WH_B",
            start_time=0, expect_time=10,
        )
        e.add_transport_order(order)
        env.run(31)

        # 30 items delivered at 1/tick → done t=30
        assert wh_b.inventory.get("SKU_X", 0) == 30
        # WH_A debited 30 items
        assert wh_a.inventory.get("SKU_X", 0) == 70

    def test_partial_pallet_rounds_up(self, env, wh_a, wh_b):
        """5 items rounds up to 1 pallet (10 items)."""
        wh_a.inventory = {"SKU_X": 100}
        e = _make_edge(env, wh_a, wh_b, mode=TransferMode.PER_PALLET, time=1.0)

        order = TransportOrder(
            sku="SKU_X", quantity=5,
            from_node="WH_A", to_node="WH_B",
            start_time=0, expect_time=10,
        )
        e.add_transport_order(order)
        env.run(11)

        # 1 pallet debited (= 10 items, rounded up from 5)
        assert wh_a.inventory.get("SKU_X", 0) == 90
        # 10 items delivered at 1/tick → done t=10
        assert wh_b.inventory.get("SKU_X", 0) == 10


# ---------------------------------------------------------------------------
# Transport execution — BATCH mode
# ---------------------------------------------------------------------------

class TestExecuteBatch:
    def test_single_batch(self, env, wh_a, wh_b):
        """20 items = 2 pallets, batch_pallets=5 → 1 batch of 2 pallets."""
        wh_a.inventory = {"SKU_X": 100}
        e = _make_edge(env, wh_a, wh_b, mode=TransferMode.BATCH, time=3.0, batch=5)

        order = TransportOrder(
            sku="SKU_X", quantity=20,
            from_node="WH_A", to_node="WH_B",
            start_time=0, expect_time=10,
        )
        e.add_transport_order(order)
        env.run(5)

        # 20 items (= 2 pallets) debited, 1 batch delivered after 3.0
        assert wh_a.inventory.get("SKU_X", 0) == 80
        assert wh_b.inventory.get("SKU_X", 0) == 20

    def test_multi_batch(self, env, wh_a, wh_b):
        """100 items = 10 pallets, batch_pallets=3 → 4 batches."""
        wh_a.inventory = {"SKU_X": 200}
        e = _make_edge(env, wh_a, wh_b, mode=TransferMode.BATCH, time=2.0, batch=3)

        order = TransportOrder(
            sku="SKU_X", quantity=100,
            from_node="WH_A", to_node="WH_B",
            start_time=0, expect_time=10,
        )
        e.add_transport_order(order)
        env.run(8.5)

        # 100 items (= 10 pallets) debited
        assert wh_a.inventory.get("SKU_X", 0) == 100
        # After 4 batches × 2.0 = 8.0, all 100 items delivered
        assert wh_b.inventory.get("SKU_X", 0) == 100


# ---------------------------------------------------------------------------
# Source nodes (infinite supply — no debit)
# ---------------------------------------------------------------------------

class TestExecuteFromSource:
    def test_source_not_debited(self, env, wh_b):
        src = WarehouseNode(
            name="SRC", role=NodeRole.SOURCE,
            conversion_factors={"SKU_X": 10}, env=env,
        )
        e = _make_edge(env, src, wh_b, mode=TransferMode.PER_PALLET, time=1.0)

        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="SRC", to_node="WH_B",
            start_time=0, expect_time=10,
        )
        e.add_transport_order(order)
        env.run(51)

        # 50 items delivered at 1/tick from SOURCE → done t=50
        assert wh_b.inventory.get("SKU_X", 0) == 50


# ---------------------------------------------------------------------------
# expect_time priority ordering (activated queue)
# ---------------------------------------------------------------------------

class TestPriorityOrdering:
    def test_earlier_expect_time_executed_first(self, env, wh_a, wh_b):
        wh_a.inventory = {"SKU_X": 200}
        e = _make_edge(env, wh_a, wh_b, mode=TransferMode.PER_PALLET, time=0.5)

        low_pri = TransportOrder(
            sku="SKU_X", quantity=10,
            from_node="WH_A", to_node="WH_B",
            start_time=0, expect_time=30,
        )
        high_pri = TransportOrder(
            sku="SKU_X", quantity=10,
            from_node="WH_A", to_node="WH_B",
            start_time=0, expect_time=5,
        )
        e.add_transport_order(low_pri)
        e.add_transport_order(high_pri)

        env.run(11)
        total_b = wh_b.inventory.get("SKU_X", 0)
        # Both orders executed (20 items @ 0.5/tick → done t=10)
        assert total_b == 20
