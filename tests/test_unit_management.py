"""Unit tests for Edge-based transport order execution and Management.

The old ``JobManager`` has been removed; transport orders are managed by
:class:`Management` (a ``salabim.Component``) which issues static orders
onto the correct edge at the right time.
"""

import math
import pytest
import salabim as sim

from src.infrastructure.edge import Edge, TransferMode, TransportOrder
from src.infrastructure.warehouse_node import WarehouseNode, NodeRole
from src.infrastructure.production_node import ProductionNode, ProductionOrder
from src.management.static_order import StaticOrderManagement
from src.management.base import Management, Snapshot, Decision
from src.management.safe_stock_management import SafeStockManagement
from src.management.trace_management import TraceManagement
from src.management.weigh_safe_stock_management import WeighSafeStockManagement
from src.model.sku import SKU


SKU_REGISTRY_X = {"SKU_X": SKU(id="SKU_X", pallet_size=10)}
SKU_REGISTRY_RAW = {"raw": SKU(id="raw", pallet_size=100)}
SKU_REGISTRY_WORK = {
    "raw": SKU(id="raw", pallet_size=100),
    "sauce_1": SKU(id="sauce_1", pallet_size=100),
    "SKU_A": SKU(id="SKU_A", pallet_size=50),
    "SKU_X": SKU(id="SKU_X", pallet_size=50),
    "WIP_A": SKU(id="WIP_A", pallet_size=100),
    "X": SKU(id="X", pallet_size=10),
}


@pytest.fixture
def env():
    sim.yieldless(False)
    return sim.Environment(trace=False)


@pytest.fixture
def source(env):
    return WarehouseNode(
        name="Source", role=NodeRole.SOURCE,
        sku_registry=SKU_REGISTRY_X, env=env,
    )


@pytest.fixture
def wh_a(env):
    return WarehouseNode(
        name="WH_A", role=NodeRole.WAREHOUSE,
        sku_registry=SKU_REGISTRY_X, env=env, max_pallets=100,
    )


@pytest.fixture
def wh_b(env):
    return WarehouseNode(
        name="WH_B", role=NodeRole.WAREHOUSE,
        sku_registry=SKU_REGISTRY_X, env=env, max_pallets=100,
    )


@pytest.fixture
def sink(env):
    return WarehouseNode(
        name="Sink", role=NodeRole.SINK,
        sku_registry=SKU_REGISTRY_X, env=env,
    )


# ---------------------------------------------------------------------------
# Single-hop transport
# ---------------------------------------------------------------------------

class TestSingleHop:
    def test_source_to_warehouse(self, env, source, wh_a):
        e = Edge(
            from_node=source, to_node=wh_a,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
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
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
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
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
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
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
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
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )
        e2 = Edge(
            from_node=wh_a, to_node=wh_b,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )
        e3 = Edge(
            from_node=wh_b, to_node=sink,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
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
            sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=10)}, env=env,
        )

    @pytest.fixture
    def wh(self, env):
        return WarehouseNode(
            name="wh", role=NodeRole.WAREHOUSE,
            sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=10)}, env=env, max_pallets=100,
        )

    def test_issues_immediate_orders_at_t0(self, env, source, wh):
        """Orders with start_time=0 are issued on the first wake-up (t=0)."""
        e = Edge(
            from_node=source, to_node=wh,
            transfer_mode=TransferMode.BATCH,
            batch_transport_time=0.01, batch_pallets=999, env=env,
        )
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="source", to_node="wh",
            start_time=0, expect_time=10,
        )
        mgmt = StaticOrderManagement(
            transport_orders=[order], edges=[e],
            production_orders=[], nodes={},
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
            batch_transport_time=0.01, batch_pallets=999, env=env,
        )
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="source", to_node="wh",
            start_time=50, expect_time=60,
        )
        mgmt = StaticOrderManagement(
            transport_orders=[order], edges=[e],
            production_orders=[], nodes={},
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
            batch_transport_time=0.01, batch_pallets=999, env=env,
        )
        order = TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="source", to_node="wh",
            start_time=15, expect_time=30,
        )
        mgmt = StaticOrderManagement(
            transport_orders=[order], edges=[e],
            production_orders=[], nodes={},
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
            batch_transport_time=0.01, batch_pallets=999, env=env,
        )
        mgmt = StaticOrderManagement(
            transport_orders=[], edges=[e],
            production_orders=[], nodes={},
            decision_interval=10.0, env=env,
        )
        found = mgmt.find_edge("source", "wh")
        assert found is e
        assert mgmt.find_edge("source", "nonexistent") is None


# ===================================================================
# Base Management tests
# ===================================================================


@pytest.fixture
def prod_env():
    sim.yieldless(False)
    return sim.Environment(trace=False)


@pytest.fixture
def ms(prod_env):
    return WarehouseNode(
        name="MS_1", role=NodeRole.WAREHOUSE,
        sku_registry={"WIP_A": SKU(id="WIP_A", pallet_size=100), "SKU_X": SKU(id="SKU_X", pallet_size=50)}, env=prod_env, max_pallets=500,
    )


@pytest.fixture
def lineside(prod_env):
    return WarehouseNode(
        name="lineside_noodle_1", role=NodeRole.WAREHOUSE,
        sku_registry={"WIP_A": SKU(id="WIP_A", pallet_size=100)}, env=prod_env, max_pallets=100,
    )


@pytest.fixture
def prod_node(prod_env, ms, lineside):
    out = WarehouseNode(
        name="output_1", role=NodeRole.WAREHOUSE,
        sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=50)}, env=prod_env, max_pallets=200,
    )
    node = ProductionNode(
        name="noodle_1", bom={
            "SKU_X": {"inputs": {"WIP_A": 2}, "speed": 10, "lead_time": 0},
        },
        upstream_node=lineside, downstream_node=out,
        env=prod_env, global_time_step=5.0,
        sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=50), "WIP_A": SKU(id="WIP_A", pallet_size=100)},
        shift_duration=675.0,
        decision_offset=240.0,
        production_start_times=[480.0, 1200.0],
    )
    return node


class TestBaseManagement:
    """Direct tests for the base Management class."""

    def test_find_edge_success(self, prod_env, ms, lineside):
        e = Edge(from_node=ms, to_node=lineside,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        mgmt = _make_minimal_mgmt(prod_env, nodes={ms.node_name: ms}, edges=[e])
        found = mgmt.find_edge(ms.node_name, lineside.node_name)
        assert found is e

    def test_find_edge_missing(self, prod_env, ms, lineside):
        e = Edge(from_node=ms, to_node=lineside,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        mgmt = _make_minimal_mgmt(prod_env, nodes={ms.node_name: ms}, edges=[e])
        assert mgmt.find_edge("nonexistent", lineside.node_name) is None

    def test_production_nodes_detected(self, prod_env, ms, lineside, prod_node):
        nodes = {ms.node_name: ms, lineside.node_name: lineside, prod_node.node_name: prod_node}
        e = Edge(from_node=lineside, to_node=ms,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        mgmt = _make_minimal_mgmt(prod_env, nodes=nodes, edges=[e])
        assert prod_node.node_name in mgmt._production_nodes

    def test_non_production_nodes_excluded(self, prod_env, ms, lineside):
        nodes = {ms.node_name: ms, lineside.node_name: lineside}
        e = Edge(from_node=ms, to_node=lineside,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        mgmt = _make_minimal_mgmt(prod_env, nodes=nodes, edges=[e])
        assert len(mgmt._production_nodes) == 0

    def test_lineside_suppliers_structural(self, prod_env, ms, lineside, prod_node):
        """lineside node identified by being upstream of a production node, not by name."""
        nodes = {ms.node_name: ms, lineside.node_name: lineside, prod_node.node_name: prod_node}
        e = Edge(from_node=ms, to_node=lineside,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        mgmt = _make_minimal_mgmt(prod_env, nodes=nodes, edges=[e])
        assert mgmt._lineside_suppliers.get(lineside.node_name) == ms.node_name

    def test_lineside_suppliers_excludes_non_lineside(self, prod_env, ms, lineside, prod_node):
        """A node that is not upstream of any production node is not in lineside_suppliers."""
        extra = WarehouseNode(name="unrelated", role=NodeRole.WAREHOUSE,
                              sku_registry={"X": SKU(id="X", pallet_size=10)}, env=prod_env, max_pallets=100)
        nodes = {ms.node_name: ms, lineside.node_name: lineside,
                 prod_node.node_name: prod_node, extra.node_name: extra}
        e1 = Edge(from_node=ms, to_node=lineside,
                  transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        e2 = Edge(from_node=ms, to_node=extra,
                  transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        mgmt = _make_minimal_mgmt(prod_env, nodes=nodes, edges=[e1, e2])
        assert extra.node_name not in mgmt._lineside_suppliers

    def test_gather_info_storage_stock(self, prod_env, ms, lineside):
        ms.inventory = {"WIP_A": 500}
        e = Edge(from_node=ms, to_node=lineside,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        mgmt = _make_minimal_mgmt(prod_env, nodes={ms.node_name: ms, lineside.node_name: lineside}, edges=[e])
        info = mgmt.gather_info()
        assert info.storage_stock.get(ms.node_name, {}).get("WIP_A") == 500

    def test_gather_info_source_nodes(self, prod_env, ms, lineside):
        src = WarehouseNode(name="source", role=NodeRole.SOURCE,
                            sku_registry={"X": SKU(id="X", pallet_size=10)}, env=prod_env)
        e = Edge(from_node=src, to_node=ms,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        mgmt = _make_minimal_mgmt(prod_env,
                                  nodes={src.node_name: src, ms.node_name: ms, lineside.node_name: lineside},
                                  edges=[e])
        info = mgmt.gather_info()
        assert "source" in info.source_nodes

    def test_gather_info_sink_excluded(self, prod_env, ms):
        sink = WarehouseNode(name="sink", role=NodeRole.SINK,
                             sku_registry={"X": SKU(id="X", pallet_size=10)}, env=prod_env)
        e = Edge(from_node=ms, to_node=sink,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        mgmt = _make_minimal_mgmt(prod_env,
                                  nodes={ms.node_name: ms, sink.node_name: sink}, edges=[e])
        info = mgmt.gather_info()
        assert sink.node_name not in info.storage_stock

    def test_gather_info_production_queues(self, prod_env, ms, lineside, prod_node):
        nodes = {ms.node_name: ms, lineside.node_name: lineside, prod_node.node_name: prod_node}
        e = Edge(from_node=lineside, to_node=ms,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        prod_node.add_production_order(ProductionOrder(
            order_id=1, sku="SKU_X", quantity=100, activate_time=0,
            expect_time=100, node_name=prod_node.node_name,
        ))
        mgmt = _make_minimal_mgmt(prod_env, nodes=nodes, edges=[e])
        info = mgmt.gather_info()
        assert len(info.production_queues.get(prod_node.node_name, [])) == 1

    def test_gather_info_edge_queues(self, prod_env, ms, lineside):
        e = Edge(from_node=ms, to_node=lineside,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=prod_env)
        key = f"{ms.node_name}->{lineside.node_name}"
        order = TransportOrder(sku="WIP_A", quantity=50, from_node=ms.node_name,
                               to_node=lineside.node_name, start_time=99, expect_time=100)
        e.add_transport_order(order)
        mgmt = _make_minimal_mgmt(prod_env,
                                  nodes={ms.node_name: ms, lineside.node_name: lineside}, edges=[e])
        info = mgmt.gather_info()
        assert len(info.edge_pending.get(key, [])) == 1


# ===================================================================
# SafeStockManagement tests
# ===================================================================


class TestSafeStockManagement:

    def _make_mgmt(self, env, safe_stock_config, nodes, edges,
                   demand_orders=None):
        return SafeStockManagement(
            safe_stock_config=safe_stock_config, nodes=nodes, edges=edges,
            demand_orders=demand_orders,
            decision_interval=10.0, env=env,
        )

    def test_demand_order_issuance(self, env):
        ms = WarehouseNode(name="fg_storage", role=NodeRole.WAREHOUSE,
                           sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=50)}, env=env, max_pallets=500)
        sink = WarehouseNode(name="sink", role=NodeRole.SINK,
                              sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=50)}, env=env)
        e = Edge(from_node=ms, to_node=sink, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[],
            nodes={ms.node_name: ms, sink.node_name: sink}, edges=[e],
            demand_orders=[{"sku": "SKU_X", "quantity": 100, "start_time": 0}],
        )
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        assert len(decision.transport_orders) == 1
        assert decision.transport_orders[0].sku == "SKU_X"
        assert decision.transport_orders[0].quantity == 100

    def test_demand_order_delayed_not_issued(self, env):
        ms = WarehouseNode(name="fg_storage", role=NodeRole.WAREHOUSE,
                           sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=50)}, env=env, max_pallets=500)
        sink = WarehouseNode(name="sink", role=NodeRole.SINK,
                              sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=50)}, env=env)
        e = Edge(from_node=ms, to_node=sink, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[],
            nodes={ms.node_name: ms, sink.node_name: sink}, edges=[e],
            demand_orders=[{"sku": "SKU_X", "quantity": 100, "start_time": 50}],
        )
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(10, info)
        assert len(decision.transport_orders) == 0

    def test_demand_order_issued_only_once(self, env):
        ms = WarehouseNode(name="fg_storage", role=NodeRole.WAREHOUSE,
                           sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=50)}, env=env, max_pallets=500)
        sink = WarehouseNode(name="sink", role=NodeRole.SINK,
                              sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=50)}, env=env)
        e = Edge(from_node=ms, to_node=sink, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[],
            nodes={ms.node_name: ms, sink.node_name: sink}, edges=[e],
            demand_orders=[{"sku": "SKU_X", "quantity": 100, "start_time": 0}],
        )
        info = mgmt.gather_info()
        decision1 = mgmt.make_decisions(0, info)
        decision2 = mgmt.make_decisions(10, info)
        assert len(decision1.transport_orders) == 1
        assert len(decision2.transport_orders) == 0

    def test_push_fires_when_stock_exists(self, env):
        src = WarehouseNode(name="buffer", role=NodeRole.WAREHOUSE,
                            sku_registry={"WIP_A": SKU(id="WIP_A", pallet_size=100)}, env=env, max_pallets=200)
        dst = WarehouseNode(name="storage", role=NodeRole.WAREHOUSE,
                            sku_registry={"WIP_A": SKU(id="WIP_A", pallet_size=100)}, env=env, max_pallets=500)
        src.inventory = {"WIP_A": 50}
        e = Edge(from_node=src, to_node=dst, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[
                dict(sku="WIP_A", safe_stock=100, replenish_qty=80,
                     storage="buffer", push_to="storage"),
            ],
            nodes={src.node_name: src, dst.node_name: dst}, edges=[e],
        )
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        assert len(decision.transport_orders) == 1
        assert decision.transport_orders[0].from_node == "buffer"
        assert decision.transport_orders[0].to_node == "storage"

    def test_push_not_fired_when_stock_zero(self, env):
        src = WarehouseNode(name="buffer", role=NodeRole.WAREHOUSE,
                            sku_registry={"WIP_A": SKU(id="WIP_A", pallet_size=100)}, env=env, max_pallets=200)
        dst = WarehouseNode(name="storage", role=NodeRole.WAREHOUSE,
                            sku_registry={"WIP_A": SKU(id="WIP_A", pallet_size=100)}, env=env, max_pallets=500)
        e = Edge(from_node=src, to_node=dst, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[
                dict(sku="WIP_A", safe_stock=100, replenish_qty=80,
                     storage="buffer", push_to="storage"),
            ],
            nodes={src.node_name: src, dst.node_name: dst}, edges=[e],
        )
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        assert len(decision.transport_orders) == 0

    def test_produce_at_fires_below_safe_stock(self, env, prod_env, ms, lineside, prod_node):
        nodes = {ms.node_name: ms, lineside.node_name: lineside, prod_node.node_name: prod_node}
        e = Edge(from_node=lineside, to_node=ms,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[
                dict(sku="SKU_X", safe_stock=200, replenish_qty=100,
                     storage="output_1", produce_at=prod_node.node_name),
            ],
            nodes=nodes, edges=[e],
        )
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        assert len(decision.production_orders) == 1
        assert decision.production_orders[0].sku == "SKU_X"

    def test_produce_at_skipped_above_safe_stock(self, env, prod_env, ms, lineside, prod_node):
        out = prod_node.downstream_node
        out.inventory = {"SKU_X": 999}
        nodes = {ms.node_name: ms, lineside.node_name: lineside, prod_node.node_name: prod_node,
                 out.node_name: out}
        e = Edge(from_node=lineside, to_node=ms,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[
                dict(sku="SKU_X", safe_stock=200, replenish_qty=100,
                     storage=out.node_name, produce_at=prod_node.node_name),
            ],
            nodes=nodes, edges=[e],
        )
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        assert len(decision.production_orders) == 0

    def test_produce_at_skipped_if_already_queued(self, env, prod_env, ms, lineside, prod_node):
        out = prod_node.downstream_node
        prod_node.add_production_order(ProductionOrder(
            order_id=1, sku="SKU_X", quantity=100, activate_time=0,
            expect_time=100, node_name=prod_node.node_name,
        ))
        nodes = {ms.node_name: ms, lineside.node_name: lineside, prod_node.node_name: prod_node,
                 out.node_name: out}
        e = Edge(from_node=lineside, to_node=ms,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[
                dict(sku="SKU_X", safe_stock=200, replenish_qty=100,
                     storage=out.node_name, produce_at=prod_node.node_name),
            ],
            nodes=nodes, edges=[e],
        )
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        assert len(decision.production_orders) == 0

    def test_replenish_from_fires_below_safe_stock(self, env):
        src = WarehouseNode(name="source", role=NodeRole.SOURCE,
                            sku_registry={"RAW": SKU(id="RAW", pallet_size=10)}, env=env)
        storage = WarehouseNode(name="ms_1", role=NodeRole.WAREHOUSE,
                                sku_registry={"RAW": SKU(id="RAW", pallet_size=10)}, env=env, max_pallets=500)
        e = Edge(from_node=src, to_node=storage, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[
                dict(sku="RAW", safe_stock=200, replenish_qty=100,
                     storage="ms_1", replenish_from="source"),
            ],
            nodes={src.node_name: src, storage.node_name: storage}, edges=[e],
        )
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        assert len(decision.transport_orders) == 1
        assert decision.transport_orders[0].from_node == "source"

    def test_replenish_from_skipped_above_safe_stock(self, env):
        src = WarehouseNode(name="source", role=NodeRole.SOURCE,
                            sku_registry={"RAW": SKU(id="RAW", pallet_size=10)}, env=env)
        storage = WarehouseNode(name="ms_1", role=NodeRole.WAREHOUSE,
                                sku_registry={"RAW": SKU(id="RAW", pallet_size=10)}, env=env, max_pallets=500)
        storage.inventory = {"RAW": 999}
        e = Edge(from_node=src, to_node=storage, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[
                dict(sku="RAW", safe_stock=200, replenish_qty=100,
                     storage="ms_1", replenish_from="source"),
            ],
            nodes={src.node_name: src, storage.node_name: storage}, edges=[e],
        )
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        assert len(decision.transport_orders) == 0

    def test_replenish_from_source_node_infinite(self, env):
        src = WarehouseNode(name="source", role=NodeRole.SOURCE,
                            sku_registry={"RAW": SKU(id="RAW", pallet_size=10)}, env=env)
        storage = WarehouseNode(name="ms_1", role=NodeRole.WAREHOUSE,
                                sku_registry={"RAW": SKU(id="RAW", pallet_size=10)}, env=env, max_pallets=500)
        e = Edge(from_node=src, to_node=storage, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[
                dict(sku="RAW", safe_stock=200, replenish_qty=100,
                     storage="ms_1", replenish_from="source"),
            ],
            nodes={src.node_name: src, storage.node_name: storage}, edges=[e],
        )
        info = mgmt.gather_info()
        assert "source" in info.source_nodes
        decision = mgmt.make_decisions(0, info)
        assert len(decision.transport_orders) == 1

    def test_execute_decision_transport_logs_and_dispatches(self, env):
        src = WarehouseNode(name="fg_storage", role=NodeRole.SOURCE,
                            sku_registry={"X": SKU(id="X", pallet_size=10)}, env=env)
        dst = WarehouseNode(name="sink", role=NodeRole.SINK,
                            sku_registry={"X": SKU(id="X", pallet_size=10)}, env=env)
        e = Edge(from_node=src, to_node=dst, transfer_mode=TransferMode.BATCH,
                 batch_transport_time=0.01, batch_pallets=999, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[],
            nodes={src.node_name: src, dst.node_name: dst}, edges=[e],
            demand_orders=[{"sku": "X", "quantity": 50, "start_time": 0,
                            "from_node": "fg_storage", "to_node": "sink"}],
        )
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        assert len(decision.transport_orders) == 1
        mgmt._execute_decision(decision)
        assert len(e.activated_queue) >= 1 or len(e.pending_queue) >= 0
        assert any(
            entry["type"] == "transport_order_added"
            for entry in e.log
        )

    def test_execute_decision_raises_on_missing_edge(self, env):
        src = WarehouseNode(name="nonexistent_src", role=NodeRole.SOURCE,
                            sku_registry={"X": SKU(id="X", pallet_size=10)}, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[],
            nodes={src.node_name: src}, edges=[],
        )
        decision = Decision()
        decision.transport_orders.append(TransportOrder(
            order_id=1, sku="X", quantity=50,
            from_node="nonexistent_src", to_node="nowhere",
            start_time=0, expect_time=10,
        ))
        with pytest.raises(RuntimeError, match="missing edge"):
            mgmt._execute_decision(decision)

    def test_execute_decision_raises_on_missing_prod_node(self, env, prod_env, ms, lineside):
        e = Edge(from_node=ms, to_node=lineside,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, safe_stock_config=[],
            nodes={ms.node_name: ms, lineside.node_name: lineside}, edges=[e],
        )
        decision = Decision()
        decision.production_orders.append(ProductionOrder(
            order_id=1, sku="SKU_X", quantity=100,
            activate_time=0, expect_time=100, node_name="nonexistent_prod",
        ))
        with pytest.raises(RuntimeError, match="missing node"):
            mgmt._execute_decision(decision)


# ===================================================================
# TraceManagement tests
# ===================================================================


def _make_trace_env(env, demand_orders=None):
    """Build a minimal topology for TraceManagement tests."""
    src = WarehouseNode(name="source", role=NodeRole.SOURCE,
                        sku_registry={"raw": SKU(id="raw", pallet_size=100),
                                      "sauce_1": SKU(id="sauce_1", pallet_size=100),
                                      "SKU_A": SKU(id="SKU_A", pallet_size=50)}, env=env)
    ms1 = WarehouseNode(name="main_storage_1", role=NodeRole.WAREHOUSE,
                         sku_registry={"raw": SKU(id="raw", pallet_size=100),
                                       "sauce_1": SKU(id="sauce_1", pallet_size=100)},
                         env=env, max_pallets=1000)
    ls = WarehouseNode(name="lineside_noodle_1", role=NodeRole.WAREHOUSE,
                       sku_registry={"sauce_1": SKU(id="sauce_1", pallet_size=100),
                                     "raw": SKU(id="raw", pallet_size=100)},
                       env=env, max_pallets=200)
    wip_out = WarehouseNode(name="output_sauce_1", role=NodeRole.WAREHOUSE,
                            sku_registry={"sauce_1": SKU(id="sauce_1", pallet_size=100)},
                            env=env, max_pallets=200)
    noodle_out = WarehouseNode(name="output_noodle_1", role=NodeRole.WAREHOUSE,
                               sku_registry={"SKU_A": SKU(id="SKU_A", pallet_size=50)},
                               env=env, max_pallets=200)
    fg = WarehouseNode(name="fg_storage", role=NodeRole.WAREHOUSE,
                       sku_registry={"SKU_A": SKU(id="SKU_A", pallet_size=50)},
                       env=env, max_pallets=500)
    sink = WarehouseNode(name="sink", role=NodeRole.SINK,
                        sku_registry={"SKU_A": SKU(id="SKU_A", pallet_size=50)}, env=env)
    wip_storage = WarehouseNode(name="WIP_storage", role=NodeRole.WAREHOUSE,
                              sku_registry={"sauce_1": SKU(id="sauce_1", pallet_size=100)},
                              env=env, max_pallets=500)

    wip_prod = ProductionNode(
        name="sauce_prod_1", bom={
            "sauce_1": {"inputs": {"raw": 2}, "speed": 10, "lead_time": 0},
        },
        upstream_node=ls, downstream_node=wip_out,
        env=env, global_time_step=5.0,
        sku_registry={"sauce_1": SKU(id="sauce_1", pallet_size=100), "raw": SKU(id="raw", pallet_size=100)},
    )
    noodle_prod = ProductionNode(
        name="noodle_prod_1", bom={
            "SKU_A": {"inputs": {"sauce_1": 3}, "speed": 10, "lead_time": 0},
        },
        upstream_node=ls, downstream_node=noodle_out,
        env=env, global_time_step=5.0,
        sku_registry={"SKU_A": SKU(id="SKU_A", pallet_size=50), "sauce_1": SKU(id="sauce_1", pallet_size=100)},
    )

    edges = [
        Edge(from_node=src, to_node=ms1, transfer_mode=TransferMode.PER_PALLET,
             batch_transport_time=1.0, env=env),
        Edge(from_node=ms1, to_node=ls, transfer_mode=TransferMode.PER_PALLET,
             batch_transport_time=1.0, env=env),
        Edge(from_node=wip_out, to_node=wip_storage, transfer_mode=TransferMode.PER_PALLET,
             batch_transport_time=1.0, env=env),
        Edge(from_node=wip_storage, to_node=ms1, transfer_mode=TransferMode.PER_PALLET,
             batch_transport_time=1.0, env=env),
        Edge(from_node=noodle_out, to_node=fg, transfer_mode=TransferMode.PER_PALLET,
             batch_transport_time=1.0, env=env),
        Edge(from_node=fg, to_node=sink, transfer_mode=TransferMode.PER_PALLET,
             batch_transport_time=1.0, env=env),
    ]

    nodes = {n.node_name: n for n in
             [src, ms1, ls, wip_out, noodle_out, fg, sink, wip_storage, wip_prod, noodle_prod]}

    mgmt = TraceManagement(
        nodes=nodes, edges=edges, demand_orders=demand_orders,
        decision_interval=10.0, env=env,
    )
    return mgmt, nodes, edges


class TestTraceManagement:

    def test_pick_producer_round_robin(self, env):
        mgmt, _, _ = _make_trace_env(env)
        candidates = ["line_a", "line_b", "line_c"]
        picks = [mgmt._pick_producer("SKU_A", candidates) for _ in range(5)]
        assert picks == ["line_a", "line_b", "line_c", "line_a", "line_b"]

    def test_pick_producer_empty_returns_none(self, env):
        mgmt, _, _ = _make_trace_env(env)
        assert mgmt._pick_producer("SKU_A", []) is None

    def test_add_transport_pallet_rounding(self, env):
        mgmt, nodes, _ = _make_trace_env(env)
        decision = Decision()
        mgmt._add_transport(decision, "main_storage_1", "lineside_noodle_1",
                            "raw", 15, 0)
        assert len(decision.transport_orders) == 1
        assert decision.transport_orders[0].quantity == 100

    def test_add_transport_missing_edge_raises(self, env):
        mgmt, _, _ = _make_trace_env(env)
        decision = Decision()
        with pytest.raises(ValueError, match="No edge"):
            mgmt._add_transport(decision, "nowhere", "nonexistent", "raw", 10, 0)

    def test_add_production_pallet_rounding(self, env):
        mgmt, nodes, _ = _make_trace_env(env)
        decision = Decision()
        mgmt._add_production(decision, "noodle_prod_1", "SKU_A", 60, 0)
        assert len(decision.production_orders) == 1
        assert decision.production_orders[0].quantity == 100

    def test_add_production_unknown_node_raises(self, env):
        mgmt, nodes, _ = _make_trace_env(env)
        decision = Decision()
        with pytest.raises(ValueError, match="not found"):
            mgmt._add_production(decision, "main_storage_1", "unknown", 75, 0)

    def test_pallet_qty_uses_pallet_size(self, env):
        mgmt, _, _ = _make_trace_env(env)
        assert mgmt._rounded_up_full_pallets_qty("main_storage_1", "sauce_1", 150) == 200

    def test_pallet_qty_missing_sku_raises(self, env):
        mgmt, _, _ = _make_trace_env(env)
        with pytest.raises(ValueError, match="not found"):
            mgmt._rounded_up_full_pallets_qty("main_storage_1", "unknown", 50)

    def test_rounded_qty(self, env):
        mgmt, _, _ = _make_trace_env(env)
        assert mgmt._rounded_qty("source", "main_storage_1", "raw", 150) == 200

    def test_rounded_qty_missing_edge_raises(self, env):
        mgmt, _, _ = _make_trace_env(env)
        with pytest.raises(ValueError, match="No edge"):
            mgmt._rounded_qty("nowhere", "nonexistent", "raw", 10)

    def test_make_decisions_empty_when_all_consumed(self, env):
        mgmt, _, _ = _make_trace_env(env)
        assert mgmt._next_demand_idx >= len(mgmt._demand_orders)
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        assert len(decision.transport_orders) == 0
        assert len(decision.production_orders) == 0

    def test_make_decisions_full_tree(self, env):
        mgmt, _, _ = _make_trace_env(env, demand_orders=[
            {"sku": "SKU_A", "quantity": 100, "from_node": "fg_storage",
             "to_node": "sink", "start_time": 0},
        ])
        info = mgmt.gather_info()
        decision = mgmt.make_decisions(0, info)
        # Should have: FG transport, FG prod, WIP prod, WIP→MS transport,
        # MS→lineside transport, source→MS transport
        assert len(decision.transport_orders) >= 3
        assert len(decision.production_orders) >= 1
        # FG production for SKU_A
        fg_prods = [o for o in decision.production_orders if o.sku == "SKU_A"]
        assert len(fg_prods) == 1
        # Raw material sourcing
        src_orders = [o for o in decision.transport_orders if o.from_node == "source"]
        assert len(src_orders) >= 1

    def test_accum_fg_tree_unknown_sku_skips_gracefully(self, env):
        mgmt, _, _ = _make_trace_env(env)
        tx_acc = {}
        prod_acc = {}
        mgmt._accum_fg_tree(tx_acc, prod_acc, "UNKNOWN_SKU", 100, 0)
        assert len(tx_acc) == 0
        assert len(prod_acc) == 0

    def test_accum_tx_accumulates(self, env):
        mgmt, _, _ = _make_trace_env(env)
        acc = {}
        mgmt._accum_tx(acc, "a", "b", "x", 50)
        mgmt._accum_tx(acc, "a", "b", "x", 30)
        assert acc[("a", "b", "x")] == 80

    def test_accum_prod_accumulates(self, env):
        mgmt, _, _ = _make_trace_env(env)
        acc = {}
        mgmt._accum_prod(acc, "node1", "x", 100)
        mgmt._accum_prod(acc, "node1", "x", 50)
        assert acc[("node1", "x")] == 150


# ===================================================================
# WeighSafeStockManagement tests
# ===================================================================


class TestWeighSafeStockManagement:

    def _make_mgmt(self, env, safe_stock_config=None, nodes=None, edges=None,
                   demand_orders=None, **kwargs):
        if nodes is None:
            nodes = {}
        if edges is None:
            edges = []
        # 如果没有传入生产节点，创建一个默认的用于测试决策时间逻辑
        has_prod_node = any(isinstance(node, ProductionNode) for node in nodes.values())
        if not has_prod_node:
            # 创建一个最小的生产节点来支持决策时间测试
            ms = WarehouseNode(
                name="test_ms", role=NodeRole.WAREHOUSE,
                sku_registry={"SKU_TEST": SKU(id="SKU_TEST", pallet_size=100)},
                env=env,
            )
            lineside = WarehouseNode(
                name="test_lineside", role=NodeRole.WAREHOUSE,
                sku_registry={"SKU_TEST": SKU(id="SKU_TEST", pallet_size=100)},
                env=env,
            )
            out = WarehouseNode(
                name="test_out", role=NodeRole.WAREHOUSE,
                sku_registry={"SKU_TEST": SKU(id="SKU_TEST", pallet_size=100)},
                env=env,
            )
            prod_node = ProductionNode(
                name="test_prod",
                bom={"SKU_TEST": {"inputs": {}, "speed": 1.0, "lead_time": 0}},
                upstream_node=lineside,
                downstream_node=out,
                env=env,
                global_time_step=5.0,
                sku_registry={"SKU_TEST": SKU(id="SKU_TEST", pallet_size=100)},
                shift_duration=675.0,
                decision_offset=240.0,
                production_start_times=[480.0, 1200.0],
            )
            nodes.update({
                ms.node_name: ms,
                lineside.node_name: lineside,
                out.node_name: out,
                prod_node.node_name: prod_node,
            })
        else:
            # 设置默认的 shift 参数到所有 ProductionNode
            for node in nodes.values():
                if isinstance(node, ProductionNode):
                    if node.shift_duration is None:
                        node.shift_duration = 675.0
                    if node.decision_offset is None:
                        node.decision_offset = 240.0
                    if node.production_start_times is None:
                        node.production_start_times = [480.0, 1200.0]
        params = dict(
            safe_stock_config=safe_stock_config or [],
            nodes=nodes, edges=edges,
            demand_orders=demand_orders or [],
            decision_interval=10.0, env=env,
        )
        params.update(kwargs)
        return WeighSafeStockManagement(**params)

    def test_is_decision_time_exact(self, env):
        mgmt = self._make_mgmt(env)
        # prod_start=480, offset=240 → decision time = 480-240 = 240
        assert mgmt._is_decision_time(240) is True

    def test_is_decision_time_not_match(self, env):
        mgmt = self._make_mgmt(env)
        assert mgmt._is_decision_time(100) is False

    def test_next_decision_time(self, env):
        mgmt = self._make_mgmt(env)
        dt = mgmt._next_decision_time(0)
        # next decision: 480-240 = 240
        assert dt == 240

    def test_next_production_start(self, env):
        mgmt = self._make_mgmt(env)
        # 获取创建的生产节点名称
        line_name = next(iter(mgmt._production_nodes.keys()))
        assert mgmt._line_production_start(line_name, 240) == 480

    def test_pick_line_round_robin_sorted(self, env):
        mgmt = self._make_mgmt(env)
        picks = [mgmt._pick_line("SKU_A", ["line_c", "line_a", "line_b"])
                 for _ in range(5)]
        assert picks == ["line_a", "line_b", "line_c", "line_a", "line_b"]

    def test_pick_line_no_candidates_raises(self, env):
        mgmt = self._make_mgmt(env)
        with pytest.raises(ValueError, match="No candidate"):
            mgmt._pick_line("SKU_A", [])

    def test_compute_shortage_ratios(self, env):
        mgmt = self._make_mgmt(env)
        mgmt._active_skus = {"SKU_A", "SKU_B"}
        mgmt._safe_stock_total = {"SKU_A": 100, "SKU_B": 200}
        info = Snapshot(current_time=0)
        info.storage_stock["wh_1"] = {"SKU_A": 50, "SKU_B": 400}
        ratios = mgmt._compute_shortage_ratios(info)
        assert ratios["SKU_A"] == 0.5
        assert ratios["SKU_B"] == 2.0

    def test_compute_shortage_ratios_only_active(self, env):
        mgmt = self._make_mgmt(env)
        mgmt._active_skus = {"SKU_A"}
        mgmt._safe_stock_total = {"SKU_A": 100, "SKU_B": 200}
        info = Snapshot(current_time=0)
        info.storage_stock["wh_1"] = {"SKU_A": 50, "SKU_B": 400}
        ratios = mgmt._compute_shortage_ratios(info)
        assert "SKU_A" in ratios
        assert "SKU_B" not in ratios

    def test_issue_demand_orders(self, env):
        fg = WarehouseNode(name="fg_storage", role=NodeRole.WAREHOUSE,
                           sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=50)}, env=env, max_pallets=500)
        sink = WarehouseNode(name="sink", role=NodeRole.SINK,
                             sku_registry={"SKU_X": SKU(id="SKU_X", pallet_size=50)}, env=env)
        e = Edge(from_node=fg, to_node=sink, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(
            env, nodes={fg.node_name: fg, sink.node_name: sink}, edges=[e],
            demand_orders=[{"sku": "SKU_X", "quantity": 100, "start_time": 0}],
        )
        decision = Decision()
        mgmt._issue_demand_orders(decision, 0)
        assert len(decision.transport_orders) == 1
        assert decision.transport_orders[0].sku == "SKU_X"

    def test_trace_new_demands_24h_window(self, env):
        """Demands beyond 24h window are not traced."""
        mgmt = self._make_mgmt(env, demand_orders=[
            {"sku": "SKU_A", "quantity": 100, "start_time": 0},
            {"sku": "SKU_B", "quantity": 100, "start_time": 2000},  # beyond 24h
        ])
        assert mgmt._next_demand_idx == 0
        mgmt._trace_new_demands(100)
        # Only first demand traced (start_time=0 <= 100+1440)
        assert mgmt._next_demand_idx == 1

    def test_trace_fg_tree_adds_wip_to_active(self, env):
        """Set up a minimal topology with one FG that requires a WIP input."""
        src = WarehouseNode(name="source", role=NodeRole.SOURCE,
                            sku_registry={"raw": SKU(id="raw", pallet_size=10)}, env=env)
        ms = WarehouseNode(name="main_storage_1", role=NodeRole.WAREHOUSE,
                           sku_registry={"raw": SKU(id="raw", pallet_size=10), "wip": SKU(id="wip", pallet_size=10)},
                           env=env, max_pallets=500)
        ls = WarehouseNode(name="lineside", role=NodeRole.WAREHOUSE,
                           sku_registry={"raw": SKU(id="raw", pallet_size=10), "wip": SKU(id="wip", pallet_size=10)},
                           env=env, max_pallets=200)
        wip_out = WarehouseNode(name="output_wip", role=NodeRole.WAREHOUSE,
                                sku_registry={"wip": SKU(id="wip", pallet_size=10)}, env=env, max_pallets=200)
        fg_out = WarehouseNode(name="output_fg", role=NodeRole.WAREHOUSE,
                               sku_registry={"FG": SKU(id="FG", pallet_size=50)}, env=env, max_pallets=200)

        wip_prod = ProductionNode(
            name="wip_line", bom={"wip": {"inputs": {"raw": 2}, "speed": 10, "lead_time": 0}},
            upstream_node=ls, downstream_node=wip_out,
            env=env, global_time_step=5.0,
            sku_registry={"wip": SKU(id="wip", pallet_size=10), "raw": SKU(id="raw", pallet_size=10)},
            shift_duration=675.0,
            decision_offset=240.0,
            production_start_times=[480.0, 1200.0],
        )
        fg_prod = ProductionNode(
            name="fg_line", bom={"FG": {"inputs": {"wip": 3}, "speed": 10, "lead_time": 0}},
            upstream_node=ls, downstream_node=fg_out,
            env=env, global_time_step=5.0,
            sku_registry={"FG": SKU(id="FG", pallet_size=50), "wip": SKU(id="wip", pallet_size=10)},
            shift_duration=675.0,
            decision_offset=240.0,
            production_start_times=[480.0, 1200.0],
        )

        edges = [
            Edge(from_node=src, to_node=ms, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env),
            Edge(from_node=ms, to_node=ls, transfer_mode=TransferMode.PER_PALLET,
                 batch_transport_time=1.0, env=env),
        ]
        nodes = {n.node_name: n for n in [src, ms, ls, wip_out, fg_out, wip_prod, fg_prod]}
        mgmt = self._make_mgmt(env, nodes=nodes, edges=edges)

        mgmt._trace_fg_tree("FG", 100)
        assert "FG" in mgmt._active_skus
        assert "wip" in mgmt._active_skus

    def test_execute_decision_production_logs_and_dispatches(self, env, prod_env, ms, lineside, prod_node):
        nodes = {ms.node_name: ms, lineside.node_name: lineside, prod_node.node_name: prod_node}
        e = Edge(from_node=lineside, to_node=ms,
                 transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env)
        mgmt = self._make_mgmt(env, nodes=nodes, edges=[e])
        decision = Decision()
        decision.production_orders.append(ProductionOrder(
            order_id=1, sku="SKU_X", quantity=100,
            activate_time=0, expect_time=100, node_name=prod_node.node_name,
        ))
        mgmt._execute_decision(decision)
        assert any(
            entry["type"] == "production_job_added"
            for entry in prod_node.log
        )

    def test_execute_decision_transport_logs_and_dispatches(self, env):
        src = WarehouseNode(name="source", role=NodeRole.SOURCE,
                            sku_registry={"X": SKU(id="X", pallet_size=10)}, env=env)
        dst = WarehouseNode(name="wh", role=NodeRole.WAREHOUSE,
                            sku_registry={"X": SKU(id="X", pallet_size=10)}, env=env, max_pallets=500)
        e = Edge(from_node=src, to_node=dst, transfer_mode=TransferMode.BATCH,
                 batch_transport_time=0.01, batch_pallets=999, env=env)
        mgmt = self._make_mgmt(env, nodes={src.node_name: src, dst.node_name: dst}, edges=[e])
        decision = Decision()
        decision.transport_orders.append(TransportOrder(
            order_id=1, sku="X", quantity=50,
            from_node="source", to_node="wh",
            start_time=0, expect_time=10,
        ))
        mgmt._execute_decision(decision)
        assert any(
            entry["type"] == "transport_order_added"
            for entry in e.log
        )

    def test_execute_decision_raises_on_missing_edge(self, env):
        mgmt = self._make_mgmt(env)
        decision = Decision()
        decision.transport_orders.append(TransportOrder(
            order_id=1, sku="X", quantity=50,
            from_node="nowhere", to_node="nonexistent",
            start_time=0, expect_time=10,
        ))
        with pytest.raises(RuntimeError, match="missing edge"):
            mgmt._execute_decision(decision)

    def test_execute_decision_raises_on_missing_prod_node(self, env):
        mgmt = self._make_mgmt(env)
        decision = Decision()
        decision.production_orders.append(ProductionOrder(
            order_id=1, sku="SKU_X", quantity=100,
            activate_time=0, expect_time=100, node_name="no_such_node",
        ))
        with pytest.raises(RuntimeError, match="missing node"):
            mgmt._execute_decision(decision)


# ===================================================================
# Helper base
# ===================================================================


class _MinimalMgmt(Management):
    """Concrete subclass of Management for base-class testing."""

    def __init__(self, nodes, edges, env, **kwargs):
        self.log = []
        super().__init__(nodes=nodes, edges=edges, env=env, **kwargs)

    def make_decisions(self, time, info):
        return Decision()

    def _execute_decision(self, decision):
        pass


def _make_minimal_mgmt(env, nodes, edges):
    return _MinimalMgmt(nodes=nodes, edges=edges, env=env, decision_interval=10.0)
