"""Unit tests for WarehouseNode — pure-math methods (no simulation needed)."""

import pytest
import salabim as sim
from src.warehouse_node import WarehouseNode, NodeRole


def _make_wh(**overrides) -> WarehouseNode:
    """Helper: create a WarehouseNode with sensible defaults."""
    env = sim.Environment(trace=False)
    params = dict(
        name="TestWH",
        role=NodeRole.WAREHOUSE,
        conversion_factors={"SKU_A": 10, "SKU_B": 25},
        env=env,
        max_pallets=100,
        dispatch_interval=1.0,
        dispatch_max_pallets=5,
    )
    params.update(overrides)
    return WarehouseNode(**params)


def _make_source(**overrides) -> WarehouseNode:
    """Helper: create a Source node."""
    env = sim.Environment(trace=False)
    params = dict(
        name="TestSource",
        role=NodeRole.SOURCE,
        conversion_factors={"SKU_A": 10},
        env=env,
    )
    params.update(overrides)
    return WarehouseNode(**params)


def _make_sink(**overrides) -> WarehouseNode:
    """Helper: create a Sink node."""
    env = sim.Environment(trace=False)
    params = dict(
        name="TestSink",
        role=NodeRole.SINK,
        conversion_factors={"SKU_A": 10},
        env=env,
    )
    params.update(overrides)
    return WarehouseNode(**params)


# ---------------------------------------------------------------------------
# Pallet math
# ---------------------------------------------------------------------------

class TestPalletsForQuantity:
    def test_zero_quantity(self):
        wh = _make_wh()
        assert wh.pallets_for_quantity("SKU_A", 0) == 0

    def test_less_than_one_pallet(self):
        wh = _make_wh()
        assert wh.pallets_for_quantity("SKU_A", 1) == 1  # ceil(1/10)

    def test_exactly_one_pallet(self):
        wh = _make_wh()
        assert wh.pallets_for_quantity("SKU_A", 10) == 1

    def test_just_over_one_pallet(self):
        wh = _make_wh()
        assert wh.pallets_for_quantity("SKU_A", 11) == 2

    def test_exact_multiple(self):
        wh = _make_wh()
        assert wh.pallets_for_quantity("SKU_A", 50) == 5


class TestQuantityForPallets:
    def test_zero_pallets(self):
        wh = _make_wh()
        assert wh.quantity_for_pallets("SKU_A", 0) == 0

    def test_one_pallet(self):
        wh = _make_wh()
        assert wh.quantity_for_pallets("SKU_A", 1) == 10

    def test_multiple_pallets(self):
        wh = _make_wh()
        assert wh.quantity_for_pallets("SKU_A", 5) == 50

    def test_different_sku_factor(self):
        wh = _make_wh()
        assert wh.quantity_for_pallets("SKU_B", 3) == 75


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


class TestCanAccept:
    def test_warehouse_within_capacity(self):
        wh = _make_wh(max_pallets=100)
        wh.inventory = {"SKU_A": 30}  # 3 pallets used
        # 50 items = 5 pallets → total 8 ≤ 100 ✓
        assert wh.can_accept("SKU_A", 50) is True

    def test_warehouse_exceeds_capacity(self):
        wh = _make_wh(max_pallets=100)
        wh.inventory = {"SKU_A": 950}  # 95 pallets used
        # 100 items = 10 pallets → total 105 > 100 ✗
        assert wh.can_accept("SKU_A", 100) is False

    def test_warehouse_exact_capacity(self):
        wh = _make_wh(max_pallets=100)
        wh.inventory = {"SKU_A": 900}  # 90 pallets used
        # 100 items = 10 pallets → total 100 = 100 ✓
        assert wh.can_accept("SKU_A", 100) is True

    def test_source_always_accepts(self):
        src = _make_source()
        assert src.can_accept("SKU_A", 999999) is True

    def test_sink_always_accepts(self):
        snk = _make_sink()
        assert snk.can_accept("SKU_A", 999999) is True

    def test_negative_quantity(self):
        wh = _make_wh()
        # 0 items = 0 pallets
        assert wh.can_accept("SKU_A", 0) is True


# ---------------------------------------------------------------------------
# SKU registration
# ---------------------------------------------------------------------------

class TestAddSku:
    def test_add_new_sku(self):
        wh = _make_wh(conversion_factors={"EXISTING": 10})
        wh.add_sku("NEW_SKU", 50)
        assert wh.conversion_factors["NEW_SKU"] == 50

    def test_add_duplicate_sku_raises(self):
        wh = _make_wh(conversion_factors={"EXISTING": 10})
        with pytest.raises(ValueError, match="already exists"):
            wh.add_sku("EXISTING", 20)
