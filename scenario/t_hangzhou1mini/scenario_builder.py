"""Build the Hangzhou-0b simulation environment."""

import salabim as sim

from src.builder import (
    build_nodes,
    build_edges,
    create_management,
    SimulationContext,
)
from . import config
from . import config_static_jobs as orders_module
from . import safe_stock
from . import demand as demand_module
from . import init_stock


def create_simulation() -> SimulationContext:
    """Return a fully initialised ``SimulationContext`` for this scenario."""
    sim.yieldless(False)
    env = sim.Environment(trace=False)

    nodes = build_nodes(config, env)
    edges = build_edges(config, nodes, env)

    # Inject initial stock into warehouse nodes
    for node_name, skus in init_stock.INIT_STOCK.items():
        node = nodes.get(node_name)
        if node is not None:
            for sku, qty in skus.items():
                if qty > 0:
                    node.receive(sku, qty)

    management = create_management(
        config, orders_module, nodes, edges, env,
        safe_stock_module=safe_stock,
        demand_module=demand_module,
    )

    sku_map = getattr(config, "SKUS", {})
    if isinstance(sku_map, (list, tuple)):
        sku_map = {s: s for s in sku_map}

    return SimulationContext(
        scenario_name=__name__.rsplit(".", 1)[0],
        env=env,
        nodes=nodes,
        edges=edges,
        config=config,
        management=management,
        sku_map=sku_map,
    )
