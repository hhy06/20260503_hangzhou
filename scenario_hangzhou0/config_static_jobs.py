"""Static transport / production-order definitions for scenario_hangzhou0.

SKU IDs used in jobs / production orders:
  raw, sauce_wip, powder_wip, fg_noodle

Timeline
--------
t=0   source -> raw_material_wh             raw x 500
t=0   raw_material_wh -> seasoning_lineside raw x 300
t=0   sauce_workshop  starts: produce 100 sauce_wip  (speed=10/min -> ~10 min)
t=0   powder_workshop starts: produce 100 powder_wip (speed=10/min -> ~10 min)
t=0   semi_finished_wh -> warehouse_1/2     sauce_wip x 50, powder_wip x 50 each
t=0   warehouse_1/2 -> line_side_1/2        sauce_wip x 50, powder_wip x 50 each
t=0   finished_wh -> sink                   fg_noodle x 80
t=50  noodle_ws_1  starts: produce 40 fg_noodle  (~8 min)
t=50  noodle_ws_2  starts: produce 40 fg_noodle  (~8 min)
"""

from src.edge import TransportOrder
from src.production_node import ProductionOrder

# ---------------------------------------------------------------------------
# Transport orders — one per edge hop
# ---------------------------------------------------------------------------
TRANSPORT_ORDERS = [
    # -- raw material supply chain --
    TransportOrder(
        sku="raw", quantity=500,
        from_node="source", to_node="raw_material_wh",
        start_time=0, expect_time=10,
    ),
    TransportOrder(
        sku="raw", quantity=300,
        from_node="raw_material_wh", to_node="seasoning_lineside",
        start_time=0, expect_time=10,
    ),
    # -- WIP allocation: one SKU per destination --
    TransportOrder(
        sku="sauce_wip", quantity=50,
        from_node="semi_finished_wh", to_node="warehouse_1",
        start_time=0, expect_time=10,
    ),
    TransportOrder(
        sku="powder_wip", quantity=50,
        from_node="semi_finished_wh", to_node="warehouse_2",
        start_time=0, expect_time=10,
    ),
    # -- WIP push to noodle line-side storage --
    TransportOrder(
        sku="sauce_wip", quantity=50,
        from_node="warehouse_1", to_node="line_side_1",
        start_time=0, expect_time=10,
    ),
    TransportOrder(
        sku="powder_wip", quantity=50,
        from_node="warehouse_2", to_node="line_side_2",
        start_time=0, expect_time=10,
    ),
    # -- finished-goods shipment --
    TransportOrder(
        sku="fg_noodle", quantity=80,
        from_node="finished_wh", to_node="sink",
        start_time=0, expect_time=10,
    ),
]

# ---------------------------------------------------------------------------
# Production orders
# ---------------------------------------------------------------------------
PRODUCTION_JOBS = [
    # -- seasoning: both run in parallel from t=0 --
    ProductionOrder(
        job_id=1,
        output_sku="sauce_wip",
        quantity=100,
        start_time=0,
        node_name="sauce_workshop",
    ),
    ProductionOrder(
        job_id=2,
        output_sku="powder_wip",
        quantity=100,
        start_time=0,
        node_name="powder_workshop",
    ),
    # -- noodle making: delayed so WIPs have time to flow through --
    ProductionOrder(
        job_id=3,
        output_sku="fg_noodle",
        quantity=40,
        start_time=50,
        node_name="noodle_ws_1",
    ),
    ProductionOrder(
        job_id=4,
        output_sku="fg_noodle",
        quantity=40,
        start_time=50,
        node_name="noodle_ws_2",
    ),
]
