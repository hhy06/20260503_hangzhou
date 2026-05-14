"""Static job / production-order definitions for scenario_hangzhou0.

Timeline
--------
t=0  source -> raw_material_wh             raw x 500
t=0  raw_material_wh -> seasoning_lineside raw x 300
t=0  sauce_workshop  starts: produce 100 wip_s  (speed=10/min -> ~10 min)
t=0  powder_workshop starts: produce 100 wip_p  (speed=10/min -> ~10 min)
t=0  semi_finished_wh -> warehouse_1/2     wip_s x 50, wip_p x 50  each
t=0  warehouse_1/2 -> line_side_1/2        wip_s x 50, wip_p x 50  each
t=0  finished_wh -> sink                   fg x 80
t=50 noodle_ws_1  starts: produce 40 fg   (wip_s + wip_p → fg, ~8 min)
t=50 noodle_ws_2  starts: produce 40 fg   (wip_s + wip_p → fg, ~8 min)
"""

from src.warehouse_node import OutboundOrder
from src.management import Job
from src.production_node import ProductionOrder

# ---------------------------------------------------------------------------
# Transport / dispatch jobs  (all at t=0 — execute when inventory allows)
# ---------------------------------------------------------------------------
JOBS = [
    # -- raw material supply chain --
    Job(
        time=0,
        from_node="source",
        to_node="raw_material_wh",
        orders=[
            OutboundOrder(sku="raw", quantity=500, priority=1),
        ],
    ),
    Job(
        time=0,
        from_node="raw_material_wh",
        to_node="seasoning_lineside",
        orders=[
            OutboundOrder(sku="raw", quantity=300, priority=1),
        ],
    ),
    # -- WIP allocation: one SKU per destination to avoid dispatch cross-SKU bug --
    Job(
        time=0,
        from_node="semi_finished_wh",
        to_node="warehouse_1",
        orders=[
            OutboundOrder(sku="wip_s", quantity=50, priority=1),
        ],
    ),
    Job(
        time=0,
        from_node="semi_finished_wh",
        to_node="warehouse_2",
        orders=[
            OutboundOrder(sku="wip_p", quantity=50, priority=1),
        ],
    ),
    # -- WIP push to noodle line-side storage --
    Job(
        time=0,
        from_node="warehouse_1",
        to_node="line_side_1",
        orders=[
            OutboundOrder(sku="wip_s", quantity=50, priority=1),
        ],
    ),
    Job(
        time=0,
        from_node="warehouse_2",
        to_node="line_side_2",
        orders=[
            OutboundOrder(sku="wip_p", quantity=50, priority=1),
        ],
    ),
    # -- finished-goods shipment --
    Job(
        time=0,
        from_node="finished_wh",
        to_node="sink",
        orders=[
            OutboundOrder(sku="fg", quantity=80, priority=1),
        ],
    ),
]

# ---------------------------------------------------------------------------
# Production orders
# ---------------------------------------------------------------------------
PRODUCTION_JOBS = [
    # -- seasoning: both run in parallel from t=0 --
    ProductionOrder(
        job_id=1,
        output_sku="wip_s",
        quantity=100,
        start_time=0,
        node_name="sauce_workshop",
    ),
    ProductionOrder(
        job_id=2,
        output_sku="wip_p",
        quantity=100,
        start_time=0,
        node_name="powder_workshop",
    ),
    # -- noodle making: delayed so WIPs have time to flow through --
    ProductionOrder(
        job_id=3,
        output_sku="fg",
        quantity=40,
        start_time=50,
        node_name="noodle_ws_1",
    ),
    ProductionOrder(
        job_id=4,
        output_sku="fg",
        quantity=40,
        start_time=50,
        node_name="noodle_ws_2",
    ),
]
