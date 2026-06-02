"""Build the example simulation environment."""

import salabim as sim

from src.builder import (
    build_nodes,
    build_edges,
    create_management,
    SimulationContext,
)
from . import config
from . import config_static_jobs as orders_module


def create_simulation() -> SimulationContext:
    """Return a fully initialised ``SimulationContext`` for this scenario."""
    sim.yieldless(False)
    env = sim.Environment(trace=False)

    nodes = build_nodes(config, env)
    edges = build_edges(config, nodes, env)

    management = create_management(config, orders_module, nodes, edges, env)

    sku_map = getattr(config, "SKUS", {})
    if isinstance(sku_map, dict):
        first_val = next(iter(sku_map.values())) if sku_map else None
        if hasattr(first_val, "name"):
            sku_map = {sid: sku.name for sid, sku in sku_map.items()}
        elif isinstance(first_val, str):
            sku_map = dict(sku_map)
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
