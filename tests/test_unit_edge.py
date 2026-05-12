"""Unit tests for Edge and TransferMode."""

import pytest
from src.edge import Edge, TransferMode


class TestEdgeTransferDuration:
    """Edge.transfer_duration() — core timing math."""

    def test_batch_mode_zero_pallets(self):
        e = Edge(None, None, TransferMode.BATCH, transfer_time=5.0, batch_size=10)
        assert e.transfer_duration(0) == 0.0

    def test_batch_mode_single_partial_batch(self):
        e = Edge(None, None, TransferMode.BATCH, transfer_time=5.0, batch_size=10)
        # 1 pallet → 1 batch → 1 × 5 = 5
        assert e.transfer_duration(1) == 5.0

    def test_batch_mode_exact_one_batch(self):
        e = Edge(None, None, TransferMode.BATCH, transfer_time=5.0, batch_size=10)
        assert e.transfer_duration(10) == 5.0

    def test_batch_mode_across_batch_boundary(self):
        e = Edge(None, None, TransferMode.BATCH, transfer_time=5.0, batch_size=10)
        # 11 pallets → 2 batches → 2 × 5 = 10
        assert e.transfer_duration(11) == 10.0

    def test_batch_mode_multiple_batches(self):
        e = Edge(None, None, TransferMode.BATCH, transfer_time=3.0, batch_size=7)
        # 20 pallets → ceil(20/7) = 3 batches → 3 × 3 = 9
        assert e.transfer_duration(20) == 9.0

    def test_per_pallet_zero_pallets(self):
        e = Edge(None, None, TransferMode.PER_PALLET, transfer_time=2.0)
        assert e.transfer_duration(0) == 0.0

    def test_per_pallet_single_pallet(self):
        e = Edge(None, None, TransferMode.PER_PALLET, transfer_time=2.0)
        assert e.transfer_duration(1) == 2.0

    def test_per_pallet_multiple_pallets(self):
        e = Edge(None, None, TransferMode.PER_PALLET, transfer_time=2.5)
        assert e.transfer_duration(4) == 10.0


class TestEdgeMaxPalletsPerTransfer:
    """Edge.max_pallets_per_transfer() — per-call limit."""

    def test_per_pallet_returns_one(self):
        e = Edge(None, None, TransferMode.PER_PALLET, transfer_time=1.0)
        assert e.max_pallets_per_transfer() == 1

    def test_batch_returns_batch_size(self):
        e = Edge(None, None, TransferMode.BATCH, transfer_time=1.0, batch_size=15)
        assert e.max_pallets_per_transfer() == 15


class TestEdgeConstruction:
    """Edge creation and naming."""

    def test_invalid_batch_size_raises(self):
        with pytest.raises(ValueError, match="batch_size"):
            Edge(None, None, TransferMode.BATCH, transfer_time=1.0, batch_size=0)

    def test_per_pallet_ignores_batch_size(self):
        # batch_size < 1 is fine for PER_PALLET mode
        e = Edge(None, None, TransferMode.PER_PALLET, transfer_time=1.0, batch_size=0)
        assert e.transfer_duration(5) == 5.0

    def test_custom_name(self):
        e = Edge(None, None, TransferMode.PER_PALLET, transfer_time=1.0, name="my_edge")
        assert "my_edge" in e.name

    def test_repr(self):
        e = Edge(None, None, TransferMode.BATCH, transfer_time=3.0, batch_size=10)
        r = repr(e)
        assert "batch" in r
        assert "transfer_time=3" in r
        assert "batch_size=10" in r
