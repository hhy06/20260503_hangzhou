"""Structural validation for every scenario configuration.

Checks that each scenario folder has correctly wired config modules:
   - Required attributes exist (SKUS, NODES, EDGES, SIM_DURATION)
   - All SKU pallet_size values are set
   - All edge/node/job references point to existing nodes
   - All BOM SKU references exist in SKUS
   - All production-order SKU/node references are valid

These tests are purely structural — they do NOT run simulations.
"""

import importlib
import pytest

from src.infrastructure.edge import TransferMode, TransportOrder
from src.infrastructure.production_node import ProductionOrder


# ---------------------------------------------------------------------------
# Scenario registry  —  add new scenarios here
# ---------------------------------------------------------------------------
SCENARIOS = [
    "scenario.ss_hangzhou0b",
    "scenario.t_hangzhou1",
    "scenario.w_hangzhou1",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(name: str):
    return importlib.import_module(f"{name}.config")


def _orders(name: str):
    return importlib.import_module(f"{name}.config_static_jobs")


def _sku_keys(cfg) -> set[str]:
    """Return the set of SKU identifiers regardless of list/dict format."""
    skus = cfg.SKUS
    if isinstance(skus, dict):
        # Handle both str values and SKU objects
        first_val = next(iter(skus.values()))
        if isinstance(first_val, str):
            return set(skus.keys())
        else:
            return set(skus.keys())  # SKU objects are stored with id as key
    return set(skus)


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

class TestModuleStructure:
    """Every scenario folder must have the right modules and attributes."""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_config_module_importable(self, scenario):
        _config(scenario)

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_orders_module_importable(self, scenario):
        _orders(scenario)

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_required_config_attrs(self, scenario):
        cfg = _config(scenario)
        for attr in ("SKUS", "NODES", "EDGES", "SIM_DURATION"):
            assert hasattr(cfg, attr), f"{scenario}: config missing '{attr}'"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_sim_duration_positive(self, scenario):
        cfg = _config(scenario)
        assert cfg.SIM_DURATION > 0, f"{scenario}: SIM_DURATION must be positive"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_skus_not_empty(self, scenario):
        cfg = _config(scenario)
        assert len(cfg.SKUS) > 0, f"{scenario}: SKUS is empty"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_nodes_not_empty(self, scenario):
        cfg = _config(scenario)
        assert len(cfg.NODES) > 0, f"{scenario}: NODES is empty"


# ---------------------------------------------------------------------------
# SKU pallet_size validation
# ---------------------------------------------------------------------------

class TestSkuPalletSize:
    """Each SKU must have pallet_size set and positive."""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_all_skus_have_pallet_size(self, scenario):
        cfg = _config(scenario)
        skus = _sku_keys(cfg)
        for sku in skus:
            sku_obj = cfg.SKUS[sku]
            if hasattr(sku_obj, "pallet_size"):
                ps = sku_obj.pallet_size
                assert ps is not None and ps > 0, \
                    f"{scenario}: SKU '{sku}' pallet_size is None or not positive ({ps})"
            else:
                pytest.fail(f"{scenario}: SKU '{sku}' missing pallet_size attribute")


# ---------------------------------------------------------------------------
# Node structure
# ---------------------------------------------------------------------------

class TestNodeStructure:
    """Each node entry must have the required fields for its type."""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_all_nodes_have_type(self, scenario):
        cfg = _config(scenario)
        for name, nd in cfg.NODES.items():
            assert "type" in nd, f"{scenario}/{name}: missing 'type'"
            assert nd["type"] in ("source", "warehouse", "sink", "production"), \
                f"{scenario}/{name}: unknown type '{nd['type']}'"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_production_nodes_have_bom(self, scenario):
        cfg = _config(scenario)
        for name, nd in cfg.NODES.items():
            if nd.get("type") != "production":
                continue
            assert "upstream" in nd, f"{scenario}/{name}: production node missing 'upstream'"
            assert "downstream" in nd, f"{scenario}/{name}: production node missing 'downstream'"
            assert "bom" in nd, f"{scenario}/{name}: production node missing 'bom'"
            assert nd["upstream"] in cfg.NODES, \
                f"{scenario}/{name}: upstream '{nd['upstream']}' not in NODES"
            assert nd["downstream"] in cfg.NODES, \
                f"{scenario}/{name}: downstream '{nd['downstream']}' not in NODES"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_warehouse_nodes_have_max_pallets(self, scenario):
        cfg = _config(scenario)
        for name, nd in cfg.NODES.items():
            if nd.get("type") not in ("warehouse",):
                continue
            assert "max_pallets" in nd, f"{scenario}/{name}: warehouse missing 'max_pallets'"
            assert nd["max_pallets"] > 0, f"{scenario}/{name}: max_pallets must be positive"


# ---------------------------------------------------------------------------
# Edge references
# ---------------------------------------------------------------------------

class TestEdgeReferences:
    """All edge from_node/to_node must exist in NODES."""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_edges_reference_existing_nodes(self, scenario):
        cfg = _config(scenario)
        nodes = set(cfg.NODES.keys())
        for i, e in enumerate(cfg.EDGES):
            assert "from_node" in e, f"{scenario} edge[{i}]: missing 'from_node'"
            assert "to_node" in e, f"{scenario} edge[{i}]: missing 'to_node'"
            assert "transfer_mode" in e, f"{scenario} edge[{i}]: missing 'transfer_mode'"
            assert isinstance(e["transfer_mode"], TransferMode), \
                f"{scenario} edge[{i}]: transfer_mode must be TransferMode enum"
            assert e["from_node"] in nodes, \
                f"{scenario} edge[{i}]: from_node '{e['from_node']}' not in NODES"
            assert e["to_node"] in nodes, \
                f"{scenario} edge[{i}]: to_node '{e['to_node']}' not in NODES"


# ---------------------------------------------------------------------------
# BOM SKU references
# ---------------------------------------------------------------------------

class TestBomSkuReferences:
    """All SKU references in production BOMs must exist in SKUS."""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_bom_output_skus_exist(self, scenario):
        cfg = _config(scenario)
        skus = _sku_keys(cfg)
        for name, nd in cfg.NODES.items():
            if nd.get("type") != "production":
                continue
            for out_sku in nd.get("bom", {}):
                assert out_sku in skus, \
                    f"{scenario}/{name}: BOM output '{out_sku}' not in SKUS"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_bom_input_skus_exist(self, scenario):
        cfg = _config(scenario)
        skus = _sku_keys(cfg)
        for name, nd in cfg.NODES.items():
            if nd.get("type") != "production":
                continue
            for out_sku, bom_entry in nd.get("bom", {}).items():
                for in_sku in bom_entry.get("inputs", {}):
                    assert in_sku in skus, \
                        f"{scenario}/{name}: BOM input '{in_sku}' for '{out_sku}' not in SKUS"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_bom_has_speed_and_lead_time(self, scenario):
        cfg = _config(scenario)
        skus = cfg.SKUS
        for name, nd in cfg.NODES.items():
            if nd.get("type") != "production":
                continue
            for out_sku, bom_entry in nd.get("bom", {}).items():
                has_speed = "speed" in bom_entry and bom_entry["speed"] > 0
                sku_obj = skus.get(out_sku) if isinstance(skus, dict) else None
                has_sku_speed = sku_obj is not None and hasattr(sku_obj, "bom_speed") and sku_obj.bom_speed > 0
                assert has_speed or has_sku_speed, \
                    f"{scenario}/{name}/{out_sku}: BOM missing 'speed' and SKU has no bom_speed"
                assert "lead_time" in bom_entry, \
                    f"{scenario}/{name}/{out_sku}: BOM missing 'lead_time'"
                assert bom_entry["lead_time"] >= 0, \
                    f"{scenario}/{name}/{out_sku}: lead_time must be >= 0"


# ---------------------------------------------------------------------------
# Transport order references
# ---------------------------------------------------------------------------

class TestTransportOrderReferences:
    """All transport orders must reference existing nodes and SKUs."""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_transport_orders_reference_valid_nodes(self, scenario):
        cfg = _config(scenario)
        om = _orders(scenario)
        nodes = set(cfg.NODES.keys())
        if not hasattr(om, "TRANSPORT_ORDERS"):
            pytest.skip(f"{scenario}: no TRANSPORT_ORDERS")
        for o in om.TRANSPORT_ORDERS:
            assert o.from_node in nodes, \
                f"{scenario}: order from_node '{o.from_node}' not in NODES"
            assert o.to_node in nodes, \
                f"{scenario}: order to_node '{o.to_node}' not in NODES"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_transport_orders_sku_references_exist(self, scenario):
        cfg = _config(scenario)
        om = _orders(scenario)
        skus = _sku_keys(cfg)
        if not hasattr(om, "TRANSPORT_ORDERS"):
            pytest.skip(f"{scenario}: no TRANSPORT_ORDERS")
        for o in om.TRANSPORT_ORDERS:
            assert o.sku in skus, \
                f"{scenario}: order SKU '{o.sku}' not in SKUS"
            assert o.quantity > 0, \
                f"{scenario}: order SKU '{o.sku}' quantity must be positive"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_production_orders_reference_valid_nodes(self, scenario):
        cfg = _config(scenario)
        om = _orders(scenario)
        if not hasattr(om, "PRODUCTION_JOBS"):
            pytest.skip(f"{scenario}: no PRODUCTION_JOBS")
        nodes = set(cfg.NODES.keys())
        for pj in om.PRODUCTION_JOBS:
            assert pj.node_name in nodes, \
                f"{scenario}: prod job #{pj.order_id} node '{pj.node_name}' not in NODES"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_production_orders_sku_references_exist(self, scenario):
        cfg = _config(scenario)
        om = _orders(scenario)
        if not hasattr(om, "PRODUCTION_JOBS"):
            pytest.skip(f"{scenario}: no PRODUCTION_JOBS")
        skus = _sku_keys(cfg)
        for pj in om.PRODUCTION_JOBS:
            assert pj.sku in skus, \
                f"{scenario}: prod job #{pj.order_id} sku '{pj.sku}' not in SKUS"
            assert pj.quantity > 0, \
                f"{scenario}: prod job #{pj.order_id} quantity must be positive"
            assert pj.activate_time >= 0, \
                f"{scenario}: prod job #{pj.order_id} activate_time must be >= 0"
