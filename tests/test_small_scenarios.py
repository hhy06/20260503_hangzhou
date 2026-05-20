"""Inline small-scenario integration tests.

These build a minimal simulation graph directly (no scenario config
directory) and run it end-to-end, verifying final inventories and goods
conservation.

Scenarios covered:
  1. Source -> Warehouse -> Sink            (basic 2-hop transport)
  2. Source -> Warehouse -> Sink (leftover) (partial delivery)
  3. Source -> Production -> Sink           (production outputs to sink)
  4. Source -> Production -> Warehouse -> Sink  (full supply chain)
  5. Multiple orders on the same edge       (sequenced orders)
  6. Start-time gating on transport orders  (order delayed)
"""

from dataclasses import dataclass

import pytest
import salabim as sim

from src.infrastructure.edge import Edge, TransferMode, TransportOrder
from src.infrastructure.warehouse_node import WarehouseNode, NodeRole
from src.infrastructure.production_node import ProductionNode, ProductionOrder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_and_check(
    nodes: dict[str, WarehouseNode | ProductionNode],
    edges: list[Edge],
    duration: float,
) -> dict[str, dict[str, int]]:
    """Run the simulation and return final warehouse inventories."""
    sim.yieldless(False)
    # Add a dummy process to drive the simulation — edges and nodes all
    # have their own process() loops, so env.run() advances all of them.
    dummy_env: sim.Environment | None = None
    for n in nodes.values():
        if hasattr(n, "env") and n.env is not None:
            dummy_env = n.env
            break
    if dummy_env is None and edges:
        dummy_env = edges[0].env

    if dummy_env is not None:
        dummy_env.run(duration)

    inventories: dict[str, dict[str, int]] = {}
    for name, node in nodes.items():
        if isinstance(node, WarehouseNode) and node.role == NodeRole.WAREHOUSE:
            inventories[name] = dict(node.inventory)
    return inventories


def _sink_received(nodes: dict[str, WarehouseNode]) -> dict[str, int]:
    """Accumulate received goods across all SINK nodes."""
    total: dict[str, int] = {}
    for node in nodes.values():
        if isinstance(node, WarehouseNode) and node.role == NodeRole.SINK:
            for sku, qty in node.received.items():
                total[sku] = total.get(sku, 0) + qty
    return total


def _find_edge(edges: list[Edge], from_node: str, to_node: str) -> Edge | None:
    for e in edges:
        if e.from_node.node_name == from_node and e.to_node.node_name == to_node:
            return e
    return None


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def env():
    sim.yieldless(False)
    return sim.Environment(trace=False)


# ===================================================================
# Scenario 1: Source -> Warehouse -> Sink
# ===================================================================

class TestSourceWarehouseSink:
    """Source ships 30 units to WH, WH forwards 30 to Sink."""

    @pytest.fixture
    def scenario(self, env):
        cf = {"SKU_X": 10}
        source = WarehouseNode(
            name="source", role=NodeRole.SOURCE,
            conversion_factors=cf, env=env,
        )
        wh = WarehouseNode(
            name="wh", role=NodeRole.WAREHOUSE,
            conversion_factors=cf, env=env, max_pallets=100,
        )
        sink = WarehouseNode(
            name="sink", role=NodeRole.SINK,
            conversion_factors=cf, env=env,
        )
        nodes = {"source": source, "wh": wh, "sink": sink}

        e1 = Edge(
            from_node=source, to_node=wh,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )
        e2 = Edge(
            from_node=wh, to_node=sink,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )
        edges = [e1, e2]

        # Hop 1: source->wh (30 items x 1/tick @ 1 min → finishes t=30)
        e1.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="source", to_node="wh",
            start_time=0, expect_time=10,
        ))
        # Hop 2: wh->sink (starts after hop 1 delivers at t=30)
        e2.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="wh", to_node="sink",
            start_time=4, expect_time=20,
        ))

        env.run(61)
        return nodes, edges

    def test_wh_empty(self, scenario):
        nodes, _ = scenario
        assert nodes["wh"].inventory.get("SKU_X", 0) == 0

    def test_sink_received_all(self, scenario):
        nodes, _ = scenario
        assert nodes["sink"].received.get("SKU_X", 0) == 30

    def test_conservation(self, scenario):
        nodes, edges = scenario
        source_out = 0
        for e in edges:
            for entry in e.log:
                if entry["type"] == "transport_started" and entry["from"] == "source":
                    source_out += entry["quantity"]
        sink_recv = nodes["sink"].received.get("SKU_X", 0)
        wh_inv = nodes["wh"].inventory.get("SKU_X", 0)
        assert source_out == sink_recv + wh_inv


# ===================================================================
# Scenario 2: Source -> Warehouse -> Sink (with leftover)
# ===================================================================

class TestSourceWarehouseSinkLeftover:
    """Source ships 50 units to WH, WH forwards only 30; 20 remain in WH."""

    @pytest.fixture
    def scenario(self, env):
        cf = {"SKU_X": 10}
        source = WarehouseNode(
            name="source", role=NodeRole.SOURCE,
            conversion_factors=cf, env=env,
        )
        wh = WarehouseNode(
            name="wh", role=NodeRole.WAREHOUSE,
            conversion_factors=cf, env=env, max_pallets=100,
        )
        sink = WarehouseNode(
            name="sink", role=NodeRole.SINK,
            conversion_factors=cf, env=env,
        )
        nodes = {"source": source, "wh": wh, "sink": sink}

        e1 = Edge(
            from_node=source, to_node=wh,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )
        e2 = Edge(
            from_node=wh, to_node=sink,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )
        edges = [e1, e2]

        # Hop 1: 50 items @ 1/tick → finishes t=50
        e1.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=50,
            from_node="source", to_node="wh",
            start_time=0, expect_time=10,
        ))
        # Hop 2: wh forwards 30 (starts after hop 1 delivers at t=50)
        e2.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="wh", to_node="sink",
            start_time=6, expect_time=20,
        ))

        env.run(81)
        return nodes, edges

    def test_wh_has_leftover(self, scenario):
        nodes, _ = scenario
        assert nodes["wh"].inventory.get("SKU_X", 0) == 20

    def test_sink_received(self, scenario):
        nodes, _ = scenario
        assert nodes["sink"].received.get("SKU_X", 0) == 30

    def test_conservation(self, scenario):
        nodes, edges = scenario
        source_out = 0
        for e in edges:
            for entry in e.log:
                if entry["type"] == "transport_started" and entry["from"] == "source":
                    source_out += entry["quantity"]
        sink_recv = nodes["sink"].received.get("SKU_X", 0)
        wh_inv = nodes["wh"].inventory.get("SKU_X", 0)
        assert source_out == sink_recv + wh_inv


# ===================================================================
# Scenario 3: Source -> Production -> Sink
# ===================================================================

class TestSourceProductionSink:
    """Production line converts raw → fg, outputs directly to Sink."""

    @pytest.fixture
    def scenario(self, env):
        cf = {"raw": 10, "fg": 10}
        source = WarehouseNode(
            name="source", role=NodeRole.SOURCE,
            conversion_factors=cf, env=env,
        )
        lineside = WarehouseNode(
            name="lineside", role=NodeRole.WAREHOUSE,
            conversion_factors=cf, env=env, max_pallets=50,
        )
        sink = WarehouseNode(
            name="sink", role=NodeRole.SINK,
            conversion_factors=cf, env=env,
        )
        prod = ProductionNode(
            name="prod",
            bom={
                "fg": {"inputs": {"raw": 1}, "speed": 5.0, "lead_time": 0},
            },
            output_conversion_factors={"fg": 10},
            upstream_node=lineside,
            downstream_node=sink,
            env=env,
            global_time_step=1.0,
        )
        nodes = {"source": source, "lineside": lineside, "prod": prod, "sink": sink}

        e1 = Edge(
            from_node=source, to_node=lineside,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )
        edges = [e1]

        # Source sends 10 raw to lineside @ 1/tick → delivered t=1..10
        e1.add_transport_order(TransportOrder(
            sku="raw", quantity=10,
            from_node="source", to_node="lineside",
            start_time=0, expect_time=5,
        ))

        # Production job starts after all raw has arrived
        prod.add_production_order(ProductionOrder(
            job_id=1, sku="fg", quantity=10,
            activate_time=12, expect_time=20, node_name="prod",
        ))

        env.run(20)
        return nodes, edges

    def test_lineside_depleted(self, scenario):
        nodes, _ = scenario
        assert nodes["lineside"].inventory.get("raw", 0) == 0

    def test_sink_received_fg(self, scenario):
        nodes, _ = scenario
        # fg = 10 items from 1:1 BOM
        assert nodes["sink"].received.get("fg", 0) == 10

    def test_production_completed(self, scenario):
        nodes, _ = scenario
        prod = nodes["prod"]
        completed = [e for e in prod.log if e["type"] == "production_completed"]
        assert len(completed) == 1


# ===================================================================
# Scenario 4: Source -> Production -> Warehouse -> Sink (full chain)
# ===================================================================

class TestSourceProductionWarehouseSink:
    """Full chain: Source → RawWH → Production → FinWH → Sink."""

    @pytest.fixture
    def scenario(self, env):
        cf = {"raw": 100, "fg": 30}
        source = WarehouseNode(
            name="source", role=NodeRole.SOURCE,
            conversion_factors=cf, env=env,
        )
        raw_wh = WarehouseNode(
            name="raw_wh", role=NodeRole.WAREHOUSE,
            conversion_factors=cf, env=env, max_pallets=200,
        )
        fin_wh = WarehouseNode(
            name="fin_wh", role=NodeRole.WAREHOUSE,
            conversion_factors=cf, env=env, max_pallets=200,
        )
        sink = WarehouseNode(
            name="sink", role=NodeRole.SINK,
            conversion_factors=cf, env=env,
        )
        prod = ProductionNode(
            name="prod",
            bom={
                "fg": {"inputs": {"raw": 1}, "speed": 10.0, "lead_time": 0},
            },
            output_conversion_factors={"fg": 50},
            upstream_node=raw_wh,
            downstream_node=fin_wh,
            env=env,
            global_time_step=1.0,
        )
        nodes = {
            "source": source, "raw_wh": raw_wh,
            "prod": prod, "fin_wh": fin_wh, "sink": sink,
        }

        e1 = Edge(
            from_node=source, to_node=raw_wh,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )
        e2 = Edge(
            from_node=fin_wh, to_node=sink,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )
        edges = [e1, e2]

        # Source ships 30 raw to raw_wh (pallet=100 → rounds to 100 items @ 1/tick → t=100)
        e1.add_transport_order(TransportOrder(
            sku="raw", quantity=30,
            from_node="source", to_node="raw_wh",
            start_time=0, expect_time=10,
        ))

        # Production consumes raw → outputs fg to fin_wh (starts after raw arrives at t=100)
        # 30 fg @ speed 10/min → 3 min production
        prod.add_production_order(ProductionOrder(
            job_id=1, sku="fg", quantity=30,
            activate_time=102, expect_time=30, node_name="prod",
        ))

        # Fin_wh ships fg to sink (after production finishes ~t=105)
        e2.add_transport_order(TransportOrder(
            sku="fg", quantity=30,
            from_node="fin_wh", to_node="sink",
            start_time=8, expect_time=20,
        ))

        env.run(140)
        return nodes, edges

    def test_sink_received_fg(self, scenario):
        nodes, _ = scenario
        assert nodes["sink"].received.get("fg", 0) == 30

    def test_fin_wh_empty(self, scenario):
        nodes, _ = scenario
        assert nodes["fin_wh"].inventory.get("fg", 0) == 0

    def test_raw_delivered_and_partially_consumed(self, scenario):
        nodes, _ = scenario
        # Order of 30 raw rounds to 1 pallet (100 raw). Production consumes
        # 30 raw (1:1 BOM for 30 fg), leaving 70 in raw_wh.
        assert nodes["raw_wh"].inventory.get("raw", 0) == 70

    def test_production_completed(self, scenario):
        nodes, _ = scenario
        prod = nodes["prod"]
        completed = [e for e in prod.log if e["type"] == "production_completed"]
        assert len(completed) == 1


# ===================================================================
# Scenario 5: Multiple orders on the same edge
# ===================================================================

class TestMultipleOrdersSameEdge:
    """Three sequenced orders on one source → wh edge."""

    @pytest.fixture
    def scenario(self, env):
        cf = {"SKU_X": 10}
        source = WarehouseNode(
            name="source", role=NodeRole.SOURCE,
            conversion_factors=cf, env=env,
        )
        wh = WarehouseNode(
            name="wh", role=NodeRole.WAREHOUSE,
            conversion_factors=cf, env=env, max_pallets=500,
        )
        nodes = {"source": source, "wh": wh}

        e = Edge(
            from_node=source, to_node=wh,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )

        # Three non-overlapping orders on the same edge (10+20+30=60 items @ 1/tick → t=60)
        e.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=10,
            from_node="source", to_node="wh",
            start_time=0, expect_time=5,
        ))
        e.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=20,
            from_node="source", to_node="wh",
            start_time=2, expect_time=10,
        ))
        e.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="source", to_node="wh",
            start_time=5, expect_time=15,
        ))

        env.run(61)
        return nodes, [e]

    def test_total_in_wh(self, scenario):
        nodes, _ = scenario
        assert nodes["wh"].inventory.get("SKU_X", 0) == 60

    def test_conservation(self, scenario):
        nodes, edges = scenario
        source_out = 0
        for e in edges:
            for entry in e.log:
                if entry["type"] == "transport_started" and entry["from"] == "source":
                    source_out += entry["quantity"]
        wh_inv = nodes["wh"].inventory.get("SKU_X", 0)
        assert source_out == wh_inv


# ===================================================================
# Scenario 6: Start-time gating on transport orders
# ===================================================================

class TestStartTimeGating:
    """Transport order with start_time in the future is not executed early."""

    @pytest.fixture
    def scenario(self, env):
        cf = {"SKU_X": 10}
        source = WarehouseNode(
            name="source", role=NodeRole.SOURCE,
            conversion_factors=cf, env=env,
        )
        wh = WarehouseNode(
            name="wh", role=NodeRole.WAREHOUSE,
            conversion_factors=cf, env=env, max_pallets=100,
        )
        nodes = {"source": source, "wh": wh}

        e = Edge(
            from_node=source, to_node=wh,
            transfer_mode=TransferMode.PER_PALLET, batch_transport_time=1.0, env=env,
        )

        # Order with start_time=50 (far in the future)
        e.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="source", to_node="wh",
            start_time=50, expect_time=60,
        ))

        env.run(10)
        return nodes, [e]

    def test_nothing_delivered_before_start(self, scenario):
        nodes, _ = scenario
        assert nodes["wh"].inventory.get("SKU_X", 0) == 0

    def test_order_still_pending(self, scenario):
        _, edges = scenario
        e = edges[0]
        assert len(e.activated_queue) == 0
        assert len(e.pending_queue) == 1


# ===================================================================
# Scenario 7: BATCH mode on an edge
# ===================================================================

class TestBatchMode:
    """Edge uses BATCH transfer mode to move multiple pallets at once."""

    @pytest.fixture
    def scenario(self, env):
        cf = {"SKU_X": 10}
        source = WarehouseNode(
            name="source", role=NodeRole.SOURCE,
            conversion_factors=cf, env=env,
        )
        wh = WarehouseNode(
            name="wh", role=NodeRole.WAREHOUSE,
            conversion_factors=cf, env=env, max_pallets=200,
        )
        nodes = {"source": source, "wh": wh}

        e = Edge(
            from_node=source, to_node=wh,
            transfer_mode=TransferMode.BATCH, batch_transport_time=2.0,
            batch_pallets=5, env=env,
        )

        # 30 items = 3 pallets, batch_pallets=5 so only 1 batch needed
        e.add_transport_order(TransportOrder(
            sku="SKU_X", quantity=30,
            from_node="source", to_node="wh",
            start_time=0, expect_time=10,
        ))

        env.run(10)
        return nodes, [e]

    def test_all_delivered(self, scenario):
        nodes, _ = scenario
        assert nodes["wh"].inventory.get("SKU_X", 0) == 30

    def test_conservation(self, scenario):
        nodes, edges = scenario
        source_out = 0
        for e in edges:
            for entry in e.log:
                if entry["type"] == "transport_started" and entry["from"] == "source":
                    source_out += entry["quantity"]
        wh_inv = nodes["wh"].inventory.get("SKU_X", 0)
        assert source_out == wh_inv
