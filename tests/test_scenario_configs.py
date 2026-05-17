"""Structural validation for every scenario configuration.

Checks that each scenario folder has correctly wired config modules:
  - Required attributes exist (SKUS, PALLET_SIZE, NODES, EDGES, SIM_DURATION)
  - SKUS ↔ PALLET_SIZE keys align
  - All edge/node/job references point to existing nodes
  - All BOM SKU references exist in SKUS
  - All production-order SKU/node references are valid

These tests are purely structural — they do NOT run simulations.
"""

import importlib
import pytest

from src.edge import TransferMode
from src.production_node import ProductionOrder
from src.management import Job


# ---------------------------------------------------------------------------
# Scenario registry  —  add new scenarios here
# ---------------------------------------------------------------------------
SCENARIOS = [
    "test_scenario2",
    "scenario_hangzhou0",
    "scenario_hangzhou1",
    "scenario_production",
    "scenario_spws",
    "scenario_spws2",
    "scenario_spws3",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(name: str):
    return importlib.import_module(f"{name}.config")


def _jobs(name: str):
    return importlib.import_module(f"{name}.config_static_jobs")


def _sku_keys(cfg) -> set[str]:
    """Return the set of SKU identifiers regardless of list/dict format."""
    skus = cfg.SKUS
    if isinstance(skus, dict):
        return set(skus.keys())
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
    def test_jobs_module_importable(self, scenario):
        _jobs(scenario)

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_required_config_attrs(self, scenario):
        cfg = _config(scenario)
        for attr in ("SKUS", "PALLET_SIZE", "NODES", "EDGES", "SIM_DURATION"):
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
# SKUS ↔ PALLET_SIZE alignment
# ---------------------------------------------------------------------------

class TestSkuPalletAlignment:
    """SKUS and PALLET_SIZE must use exactly the same set of keys."""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_pallet_size_keys_match_skus(self, scenario):
        cfg = _config(scenario)
        skus = _sku_keys(cfg)
        pallet = set(cfg.PALLET_SIZE.keys())
        missing_in_pallet = skus - pallet
        extra_in_pallet = pallet - skus
        msg_parts = []
        if missing_in_pallet:
            msg_parts.append(f"SKUs missing from PALLET_SIZE: {missing_in_pallet}")
        if extra_in_pallet:
            msg_parts.append(f"extra keys in PALLET_SIZE: {extra_in_pallet}")
        assert not msg_parts, f"{scenario}: {'; '.join(msg_parts)}"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_pallet_size_values_positive(self, scenario):
        cfg = _config(scenario)
        for sku, val in cfg.PALLET_SIZE.items():
            assert val > 0, f"{scenario}: PALLET_SIZE['{sku}'] = {val}, must be positive"


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
    def test_production_nodes_have_bom_and_conversion_factors(self, scenario):
        cfg = _config(scenario)
        for name, nd in cfg.NODES.items():
            if nd.get("type") != "production":
                continue
            assert "upstream" in nd, f"{scenario}/{name}: production node missing 'upstream'"
            assert "downstream" in nd, f"{scenario}/{name}: production node missing 'downstream'"
            assert "bom" in nd, f"{scenario}/{name}: production node missing 'bom'"
            assert "conversion_factors" in nd, \
                f"{scenario}/{name}: production node missing 'conversion_factors'"
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
    def test_conversion_factor_skus_exist(self, scenario):
        cfg = _config(scenario)
        skus = _sku_keys(cfg)
        for name, nd in cfg.NODES.items():
            if nd.get("type") != "production":
                continue
            for conv_sku in nd.get("conversion_factors", {}):
                assert conv_sku in skus, \
                    f"{scenario}/{name}: conversion_factors key '{conv_sku}' not in SKUS"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_bom_has_speed_and_lead_time(self, scenario):
        cfg = _config(scenario)
        for name, nd in cfg.NODES.items():
            if nd.get("type") != "production":
                continue
            for out_sku, bom_entry in nd.get("bom", {}).items():
                assert "speed" in bom_entry, \
                    f"{scenario}/{name}/{out_sku}: BOM missing 'speed'"
                assert bom_entry["speed"] > 0, \
                    f"{scenario}/{name}/{out_sku}: speed must be positive"
                assert "lead_time" in bom_entry, \
                    f"{scenario}/{name}/{out_sku}: BOM missing 'lead_time'"
                assert bom_entry["lead_time"] >= 0, \
                    f"{scenario}/{name}/{out_sku}: lead_time must be >= 0"


# ---------------------------------------------------------------------------
# Job references
# ---------------------------------------------------------------------------

class TestJobReferences:
    """All jobs must reference existing nodes and SKUs."""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_transport_jobs_reference_valid_nodes(self, scenario):
        cfg = _config(scenario)
        jm = _jobs(scenario)
        nodes = set(cfg.NODES.keys())
        for j in jm.JOBS:
            assert j.from_node in nodes, \
                f"{scenario}: job from_node '{j.from_node}' not in NODES"
            assert j.to_node in nodes, \
                f"{scenario}: job to_node '{j.to_node}' not in NODES"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_transport_jobs_sku_references_exist(self, scenario):
        cfg = _config(scenario)
        jm = _jobs(scenario)
        skus = _sku_keys(cfg)
        for j in jm.JOBS:
            for o in j.orders:
                assert o.sku in skus, \
                    f"{scenario}: job order SKU '{o.sku}' not in SKUS"
                assert o.quantity > 0, \
                    f"{scenario}: job order SKU '{o.sku}' quantity must be positive"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_production_jobs_reference_valid_nodes(self, scenario):
        cfg = _config(scenario)
        jm = _jobs(scenario)
        if not hasattr(jm, "PRODUCTION_JOBS"):
            pytest.skip(f"{scenario}: no PRODUCTION_JOBS")
        nodes = set(cfg.NODES.keys())
        for pj in jm.PRODUCTION_JOBS:
            assert pj.node_name in nodes, \
                f"{scenario}: prod job #{pj.job_id} node '{pj.node_name}' not in NODES"

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_production_jobs_sku_references_exist(self, scenario):
        cfg = _config(scenario)
        jm = _jobs(scenario)
        if not hasattr(jm, "PRODUCTION_JOBS"):
            pytest.skip(f"{scenario}: no PRODUCTION_JOBS")
        skus = _sku_keys(cfg)
        for pj in jm.PRODUCTION_JOBS:
            assert pj.output_sku in skus, \
                f"{scenario}: prod job #{pj.job_id} output_sku '{pj.output_sku}' not in SKUS"
            assert pj.quantity > 0, \
                f"{scenario}: prod job #{pj.job_id} quantity must be positive"
            assert pj.start_time >= 0, \
                f"{scenario}: prod job #{pj.job_id} start_time must be >= 0"
