"""Build simulation objects from scenario configuration data.

A scenario module exports plain dicts (nodes, edges, …).  The functions
here turn those dicts into live ``salabim`` simulation objects.
"""

import math
from dataclasses import dataclass, field
from typing import Any

import salabim as sim

from src.infrastructure.edge import Edge
from src.infrastructure.warehouse_node import WarehouseNode, NodeRole
from src.infrastructure.production_node import ProductionNode
from src.management.static_order import StaticOrderManagement
from src.management.safe_stock_management import SafeStockManagement
from src.management.trace_management import TraceManagement
from src.management.weigh_safe_stock_management import WeighSafeStockManagement


# ---------------------------------------------------------------------------
# Context — pre-run simulation state
# ---------------------------------------------------------------------------


@dataclass
class SimulationContext:
    """Fully initialised simulation environment, ready to run.

    Created by a scenario's ``create_simulation()`` and consumed by
    ``main.run_scenario()`` to drive the simulation loop.
    """

    scenario_name: str
    env: sim.Environment
    nodes: dict[str, Any]
    edges: list[Edge]
    config: Any
    management: Any      # Management (static_order or safe_stock)
    sku_map: dict[str, str]


# ---------------------------------------------------------------------------
# Node / edge builder
# ---------------------------------------------------------------------------


def build_nodes(config, env: sim.Environment) -> dict[str, Any]:
    """Build all node objects in two passes.

    Pass 1 — ``source`` / ``warehouse`` / ``sink`` nodes (``WarehouseNode``).
    Pass 2 — ``production`` nodes (``ProductionNode``, requires warehouses).
    """
    nodes: dict[str, Any] = {}

    # -- Pass 1: warehouse-class nodes ------------------------------------
    for node_name, cfg in config.NODES.items():
        ntype = cfg["type"]
        if ntype in ("source", "warehouse", "sink"):
            node = WarehouseNode(
                name=node_name,
                role=NodeRole(ntype),
                sku_registry=getattr(config, "SKUS", None),
                env=env,
                max_pallets=cfg.get("max_pallets"),
                display_name=cfg.get("display_name", node_name),
            )
            nodes[node_name] = node

    # -- Pass 2: production nodes -----------------------------------------
    for node_name, cfg in config.NODES.items():
        if cfg["type"] == "production":
            node = ProductionNode(
                name=node_name,
                bom=cfg["bom"],
                upstream_node=nodes[cfg["upstream"]],
                downstream_node=nodes[cfg["downstream"]],
                env=env,
                global_time_step=cfg.get("global_time_step", 10.0),
                display_name=cfg.get("display_name", node_name),
                sku_registry=getattr(config, "SKUS", None),
                shift_duration=cfg.get("shift_duration"),
                decision_offset=cfg.get("decision_offset"),
                production_start_times=cfg.get("production_start_times"),
            )
            nodes[node_name] = node

    return nodes


def build_edges(
    config, nodes: dict[str, Any], env: sim.Environment
) -> list[Edge]:
    """Build edges and register them with their incident nodes."""
    edges = []
    for ecfg in config.EDGES:
        from_node = nodes[ecfg["from_node"]]
        to_node = nodes[ecfg["to_node"]]
        edge = Edge(
            from_node=from_node,
            to_node=to_node,
            transfer_mode=ecfg["transfer_mode"],
            batch_transport_time=ecfg["batch_transport_time"],
            batch_pallets=ecfg.get("batch_pallets", 1),
            env=env,
        )
        from_node.add_edge_out(edge)
        to_node.add_edge_in(edge)
        edges.append(edge)
    return edges


# ---------------------------------------------------------------------------
# Management factory
# ---------------------------------------------------------------------------


def create_management(
    config,
    orders_module,
    nodes,
    edges,
    env,
    *,
    safe_stock_module=None,
    demand_module=None,
):
    """Instantiate the management strategy declared in *config*.

    Parameters
    ----------
    safe_stock_module : module, optional
        Module exporting ``SAFE_STOCK`` (required for safe_stock management).
    demand_module : module, optional
        Module exporting ``DEMAND_ORDERS``.  Falls back to
        ``safe_stock_module.DEMAND_ORDERS`` if not provided.
    """
    mgmt_cfg = getattr(config, "MANAGEMENT", {})
    mgmt_type = mgmt_cfg.get("type", "static_order")
    di = mgmt_cfg.get("decision_interval", 10.0)

    # Resolve demand orders from demand_module or safe_stock_module
    if demand_module is not None:
        demand_orders = getattr(demand_module, "DEMAND_ORDERS", [])
    elif safe_stock_module is not None:
        demand_orders = getattr(safe_stock_module, "DEMAND_ORDERS", [])
    else:
        demand_orders = []

    if mgmt_type == "static_order":
        transport_orders = getattr(orders_module, "TRANSPORT_ORDERS", [])
        production_orders = getattr(orders_module, "PRODUCTION_JOBS", [])
        return StaticOrderManagement(
            transport_orders=transport_orders,
            production_orders=production_orders,
            edges=edges,
            nodes=nodes,
            decision_interval=di,
            env=env,
        )

    if mgmt_type == "safe_stock":
        if safe_stock_module is None:
            raise ValueError("safe_stock_module is required for safe_stock management")
        return SafeStockManagement(
            safe_stock_config=safe_stock_module.SAFE_STOCK,
            nodes=nodes,
            edges=edges,
            demand_orders=demand_orders,
            decision_interval=di,
            env=env,
        )

    if mgmt_type == "trace":
        return TraceManagement(
            nodes=nodes,
            edges=edges,
            demand_orders=demand_orders,
            decision_interval=di,
            env=env,
        )

    if mgmt_type == "weigh_safe_stock":
        if safe_stock_module is None:
            raise ValueError("safe_stock_module is required for weigh_safe_stock management")
        return WeighSafeStockManagement(
            safe_stock_config=safe_stock_module.SAFE_STOCK,
            nodes=nodes,
            edges=edges,
            demand_orders=demand_orders,
            trace_mode=mgmt_cfg.get("trace_mode", "full"),
            transport_mode=mgmt_cfg.get("transport_mode", "full_tree"),
            decision_interval=di,
            env=env,
        )

    raise ValueError(f"Unknown management type: {mgmt_type}")
