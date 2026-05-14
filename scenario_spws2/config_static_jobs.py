"""Static job definitions for scenario_spws2.

Jobs
----
- t=0:  source -> raw_wh: supply 3000 raw material
- t=0:  warehouse -> sink: ship 100 sku_a + 200 sku_b + 300 sku_c + 400 sku_d

Production orders
-----------------
- t=0:  productionline starts sku_a x100   (speed 10/min, ~10 min)
- t=0:  productionline starts sku_b x200   (speed  5/min, ~40 min)
- t=0:  productionline starts sku_c x300   (speed  2/min, ~150 min)
- t=0:  productionline starts sku_d x400   (speed  1/min, ~400 min)

SIM_DURATION=120 → only sku_a and sku_b finish; sku_c is partial; sku_d never starts.
"""

from src.warehouse_node import OutboundOrder
from src.management import Job
from src.production_node import ProductionOrder

JOBS = [
    Job(
        time=0,
        from_node="source",
        to_node="raw_wh",
        orders=[
            OutboundOrder(sku="raw", quantity=3000, priority=1),
        ],
    ),
    Job(
        time=0,
        from_node="warehouse",
        to_node="sink",
        orders=[
            OutboundOrder(sku="sku_a", quantity=100, priority=1),
            OutboundOrder(sku="sku_b", quantity=200, priority=2),
            OutboundOrder(sku="sku_c", quantity=300, priority=3),
            OutboundOrder(sku="sku_d", quantity=400, priority=4),
        ],
    ),
]

PRODUCTION_JOBS = [
    ProductionOrder(
        job_id=1,
        output_sku="sku_a",
        quantity=100,
        start_time=0,
        node_name="productionline",
    ),
    ProductionOrder(
        job_id=2,
        output_sku="sku_b",
        quantity=200,
        start_time=0,
        node_name="productionline",
    ),
    ProductionOrder(
        job_id=3,
        output_sku="sku_c",
        quantity=300,
        start_time=0,
        node_name="productionline",
    ),
    ProductionOrder(
        job_id=4,
        output_sku="sku_d",
        quantity=400,
        start_time=0,
        node_name="productionline",
    ),
]
