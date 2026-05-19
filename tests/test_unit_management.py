"""Unit tests for Edge-based transport order execution and Management.

The old ``JobManager`` has been removed; transport orders are managed by
:class:`Management` (a ``salabim.Component``) which issues static orders
onto the correct edge at the right time.
"""

import pytest
import salabim as sim

from src.infrastructure.edge import Edge, TransferMode, TransportOrder
from src.infrastructure.warehouse_node import WarehouseNode, NodeRole
from src.management.static_order import StaticOrderManagement


@pytest.fixture
def env():
    sim.yieldless(False)
    return sim.Environment(trace=False)


@pytest.fixture
def source(env):
    return WarehouseNode(
        name="Source", role=NodeRole.SOURCE,
        conversion_factors={"SKU_X": 10}, env=env,
    )


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


@pytest.fixture
def sink(env):
    return WarehouseNode(
        name="Sink", role=NodeRole.SINK,
        conversion_factors={"SKU_X": 10}, env=env,
    )


# ---------------------------------------------------------------------------
# Single-hop transport
# ---------------------------------------------------------------------------

class TestSingleHop:
    def test_source_to_warehouse(self, env, source, wh_a):
        e = Edge(
            from_node=source, to_node=wh_a,
            transfer_mode=TransferMode.PER_PALLET, transfer_time=1.0, env=env,
        )
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="Source", to_node="WH_A",
            start_time=0, expect_time=10,
        )
        e.add_transport_order(order)
        env.run(51)
        # Source infinite → no debit, 50 items delivered at 1/tick → done t=50
        assert wh_a.inventory.get("SKU_X", 0) == 50

    def test_warehouse_to_sink(self, env, wh_a, sink):
        wh_a.inventory = {"SKU_X": 100}
        e = Edge(
            from_node=wh_a, to_node=sink,
            transfer_mode=TransferMode.PER_PALLET, transfer_time=1.0, env=env,
        )
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="WH_A", to_node="Sink",
            start_time=0, expect_time=10,
        )
        e.add_transport_order(order)
        env.run(51)
        # WH_A debited 50 items, delivered at 1/tick → done t=50
        assert wh_a.inventory.get("SKU_X", 0) == 50
        # Sink received 50 items
        assert sink.received.get("SKU_X", 0) == 50


# ---------------------------------------------------------------------------
# Start-time gating
# ---------------------------------------------------------------------------

class TestStartTime:
    def test_order_not_executed_before_start(self, env, source, wh_a):
        e = Edge(
            from_node=source, to_node=wh_a,
            transfer_mode=TransferMode.PER_PALLET, transfer_time=1.0, env=env,
        )
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="Source", to_node="WH_A",
            start_time=50, expect_time=60,
        )
        e.add_transport_order(order)
        env.run(10)
        # t=10, start=50 → not yet activated
        assert wh_a.inventory.get("SKU_X", 0) == 0
        assert len(e.activated_queue) == 0
        assert len(e.pending_queue) == 1

    def test_order_executes_after_start(self, env, source, wh_a):
        e = Edge(
            from_node=source, to_node=wh_a,
            transfer_mode=TransferMode.PER_PALLET, transfer_time=1.0, env=env,
        )
        order = TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="Source", to_node="WH_A",
            start_time=10, expect_time=20,
        )
        e.add_transport_order(order)
        env.run(15)
        # t=15 > start=10 → should have started
        assert wh_a.inventory.get("SKU_X", 0) > 0


# ---------------------------------------------------------------------------
# Multi-hop: Source -> WH_A -> WH_B -> Sink  (3 edges, 3 orders)
# ---------------------------------------------------------------------------

class TestMultiHop:
    def test_three_hop_transport(self, env, source, wh_a, wh_b, sink):
        e1 = Edge(
            from_node=source, to_node=wh_a,
            transfer_mode=TransferMode.PER_PALLET, transfer_time=1.0, env=env,
        )
        e2 = Edge(
            from_node=wh_a, to_node=wh_b,
            transfer_mode=TransferMode.PER_PALLET, transfer_time=1.0, env=env,
        )
        e3 = Edge(
            from_node=wh_b, to_node=sink,
            transfer_mode=TransferMode.PER_PALLET, transfer_time=1.0, env=env,
        )

        # Each order corresponds to one edge hop (per spec #5).
        # Start times are staggered so hop2 debits from WH_A *after* hop1
        # has delivered (30 items @ 1 min/pallet → finishes t=3), and hop3
        # debits from WH_B after hop2 has delivered.
        hop1 = TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="Source", to_node="WH_A",
            start_time=0, expect_time=10,
        )
        hop2 = TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="WH_A", to_node="WH_B",
            start_time=4, expect_time=20,
        )
        hop3 = TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="WH_B", to_node="Sink",
            start_time=8, expect_time=30,
        )
        e1.add_transport_order(hop1)
        e2.add_transport_order(hop2)
        e3.add_transport_order(hop3)

        # PER_PALLET @ 1/tick: hop1=30t, hop2=30t, hop3=30t → all in sink by t=90
        env.run(91)

        # All 30 items should now be in the sink
        total_in_system = (
            wh_a.inventory.get("SKU_X", 0)
            + wh_b.inventory.get("SKU_X", 0)
            + sink.received.get("SKU_X", 0)
        )
        assert total_in_system == 30
        assert sink.received.get("SKU_X", 0) == 30


# ===================================================================
# Management component tests
# ===================================================================

class TestManagement:
    """Management issues static transport orders onto edges at the right time."""

    @pytest.fixture
    def env(self):
        sim.yieldless(False)
        return sim.Environment(trace=False)

    @pytest.fixture
    def source(self, env):
        return WarehouseNode(
            name="source", role=NodeRole.SOURCE,
            conversion_factors={"SKU_X": 10}, env=env,
        )

    @pytest.fixture
    def wh(self, env):
        return WarehouseNode(
            name="wh", role=NodeRole.WAREHOUSE,
            conversion_factors={"SKU_X": 10}, env=env, max_pallets=100,
        )

    def test_issues_immediate_orders_at_t0(self, env, source, wh):
        """Orders with start_time=0 are issued on the first wake-up (t=0)."""
        e = Edge(
            from_node=source, to_node=wh,
            transfer_mode=TransferMode.BATCH,
            transfer_time=0.01, batch_size=999, env=env,
        )
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="source", to_node="wh",
            start_time=0, expect_time=10,
        )
        mgmt = StaticOrderManagement(
            transport_orders=[order], edges=[e],
            decision_interval=10.0, env=env,
        )
        # Management issues order at t=0; edge wakes at t=1.0 to execute.
        env.run(1.5)
        assert wh.inventory.get("SKU_X", 0) == 50

    def test_does_not_issue_future_orders(self, env, source, wh):
        """Orders with start_time in the future are NOT issued early."""
        e = Edge(
            from_node=source, to_node=wh,
            transfer_mode=TransferMode.BATCH,
            transfer_time=0.01, batch_size=999, env=env,
        )
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="source", to_node="wh",
            start_time=50, expect_time=60,
        )
        mgmt = StaticOrderManagement(
            transport_orders=[order], edges=[e],
            decision_interval=10.0, env=env,
        )
        env.run(10)
        # At t=10, management has woken up at t=0 and t=10.
        # start_time=50 > 10 → not issued.
        assert wh.inventory.get("SKU_X", 0) == 0

    def test_issues_delayed_orders_after_start_time(self, env, source, wh):
        """Orders with start_time=15 are issued at the t=20 wake-up."""
        e = Edge(
            from_node=source, to_node=wh,
            transfer_mode=TransferMode.BATCH,
            transfer_time=0.01, batch_size=999, env=env,
        )
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="source", to_node="wh",
            start_time=15, expect_time=30,
        )
        mgmt = StaticOrderManagement(
            transport_orders=[order], edges=[e],
            decision_interval=10.0, env=env,
        )
        # t=10 → start=15 not yet
        env.run(10)
        assert wh.inventory.get("SKU_X", 0) == 0
        # t=20 → management issued order at t=20 wake-up
        env.run(25)
        assert wh.inventory.get("SKU_X", 0) == 50

    def test_find_edge_by_node_name(self, env, source, wh):
        """find_edge matches (from_node.node_name, to_node.node_name)."""
        e = Edge(
            from_node=source, to_node=wh,
            transfer_mode=TransferMode.BATCH,
            transfer_time=0.01, batch_size=999, env=env,
        )
        mgmt = StaticOrderManagement(
            transport_orders=[], edges=[e],
            decision_interval=10.0, env=env,
        )
        found = mgmt.find_edge("source", "wh")
        assert found is e
        assert mgmt.find_edge("source", "nonexistent") is None
