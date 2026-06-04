"""Unit tests for WarehouseNode — pure-math methods (no simulation needed)."""

import pytest
import salabim as sim
from src.infrastructure.warehouse_node import WarehouseNode, NodeRole
from src.model.sku import SKU


def _make_sku_registry(skus_data: dict[str, int]) -> dict[str, SKU]:
    """Create a sku_registry from a dict of {sku_id: pallet_size}."""
    return {sid: SKU(id=sid, pallet_size=ps) for sid, ps in skus_data.items()}


def _make_wh(sku_registry=None, **overrides) -> WarehouseNode:
    """Helper: create a WarehouseNode with sensible defaults."""
    env = sim.Environment(trace=False)
    if sku_registry is None:
        sku_registry = _make_sku_registry({"SKU_A": 10, "SKU_B": 25})
    params = dict(
        name="TestWH",
        role=NodeRole.WAREHOUSE,
        sku_registry=sku_registry,
        env=env,
        max_pallets=100,
    )
    params.update(overrides)
    return WarehouseNode(**params)


def _make_source(sku_registry=None, **overrides) -> WarehouseNode:
    """Helper: create a Source node."""
    env = sim.Environment(trace=False)
    if sku_registry is None:
        sku_registry = _make_sku_registry({"SKU_A": 10})
    params = dict(
        name="TestSource",
        role=NodeRole.SOURCE,
        sku_registry=sku_registry,
        env=env,
    )
    params.update(overrides)
    return WarehouseNode(**params)


def _make_sink(sku_registry=None, **overrides) -> WarehouseNode:
    """Helper: create a Sink node."""
    env = sim.Environment(trace=False)
    if sku_registry is None:
        sku_registry = _make_sku_registry({"SKU_A": 10})
    params = dict(
        name="TestSink",
        role=NodeRole.SINK,
        sku_registry=sku_registry,
        env=env,
    )
    params.update(overrides)
    return WarehouseNode(**params)


# ---------------------------------------------------------------------------
# Pallet math
# ---------------------------------------------------------------------------

class TestRoundedUpFullPalletsQty:
    def test_zero_quantity(self):
        wh = _make_wh()
        assert wh.rounded_up_full_pallets_qty("SKU_A", 0) == 0

    def test_less_than_one_pallet(self):
        wh = _make_wh()
        assert wh.rounded_up_full_pallets_qty("SKU_A", 1) == 10  # ceil(1/10)*10 = 10

    def test_exactly_one_pallet(self):
        wh = _make_wh()
        assert wh.rounded_up_full_pallets_qty("SKU_A", 10) == 10

    def test_just_over_one_pallet(self):
        wh = _make_wh()
        assert wh.rounded_up_full_pallets_qty("SKU_A", 11) == 20

    def test_exact_multiple(self):
        wh = _make_wh()
        assert wh.rounded_up_full_pallets_qty("SKU_A", 50) == 50

    def test_missing_sku_raises(self):
        wh = _make_wh()
        with pytest.raises(ValueError, match="not found in registry"):
            wh.rounded_up_full_pallets_qty("UNKNOWN_SKU", 10)


class TestQuantityOfFullPallets:
    def test_zero_pallets(self):
        wh = _make_wh()
        assert wh.quantity_of_full_pallets("SKU_A", 0) == 0

    def test_one_pallet(self):
        wh = _make_wh()
        assert wh.quantity_of_full_pallets("SKU_A", 1) == 10

    def test_multiple_pallets(self):
        wh = _make_wh()
        assert wh.quantity_of_full_pallets("SKU_A", 5) == 50

    def test_different_sku_factor(self):
        wh = _make_wh()
        assert wh.quantity_of_full_pallets("SKU_B", 3) == 75

    def test_missing_sku_raises(self):
        wh = _make_wh()
        with pytest.raises(ValueError, match="not found in registry"):
            wh.quantity_of_full_pallets("UNKNOWN_SKU", 1)


# ---------------------------------------------------------------------------
# Capacity checks
# ---------------------------------------------------------------------------

class TestCurrentPallets:
    def test_empty_warehouse(self):
        wh = _make_wh()
        assert wh.current_pallets() == 0

    def test_non_source_sink_return_zero(self):
        src = _make_source()
        assert src.current_pallets() == 0
        snk = _make_sink()
        assert snk.current_pallets() == 0

    def test_partially_filled(self):
        wh = _make_wh()
        wh.inventory = {"SKU_A": 55}  # 55 items / 10 = 6 pallets (ceil)
        assert wh.current_pallets() == 6


class TestReceiveAndCapacity:
    def test_receive_adds_to_inventory(self):
        wh = _make_wh()
        wh.receive("SKU_A", 50)
        assert wh.inventory["SKU_A"] == 50

    def test_receive_cumulative(self):
        wh = _make_wh()
        wh.receive("SKU_A", 30)
        wh.receive("SKU_A", 20)
        assert wh.inventory["SKU_A"] == 50

    def test_receive_soft_cap_no_rejection(self):
        wh = _make_wh(max_pallets=2)       # 2 pallets max
        wh.receive("SKU_A", 50)            # 50 items / 10 = 5 pallets > 2
        # Should still accept (soft cap)
        assert wh.inventory["SKU_A"] == 50
        assert wh.current_pallets() == 5

    def test_receive_to_source_noop(self):
        src = _make_source()
        src.receive("SKU_A", 999)
        # Source has no inventory
        assert not hasattr(src, "inventory") or src.inventory.get("SKU_A", 0) == 0

    def test_receive_to_sink_accumulates(self):
        snk = _make_sink()
        snk.receive("SKU_A", 100)
        snk.receive("SKU_A", 50)
        assert snk.received["SKU_A"] == 150


# ---------------------------------------------------------------------------
# SKU registration
# ---------------------------------------------------------------------------

class TestAddSku:
    def test_add_missing_sku_raises(self):
        registry = _make_sku_registry({"EXISTING": 10})
        wh = _make_wh(sku_registry=registry)
        with pytest.raises(ValueError, match="not found in registry"):
            wh.add_sku("UNKNOWN_SKU")