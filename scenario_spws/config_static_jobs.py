"""Static job definitions for scenario_spws.

Jobs
----
- t=0:  source -> raw_wh: supply 1000 raw material
- t=0:  warehouse -> sink: ship 100 sku_a + 100 sku_b

Production orders
-----------------
- t=0:  productionlien starts sku_a x100  (consumes 300 raw, speed 1/min, ~100 min)
- t=0:  productionlien starts sku_b x100  (consumes 200 raw, speed 2/min, ~50 min)
        → runs sequentially on the same line (sku_a first by job_id)
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
            OutboundOrder(sku="raw", quantity=1000, priority=1),
        ],
    ),
    Job(
        time=0,
        from_node="warehouse",
        to_node="sink",
        orders=[
            OutboundOrder(sku="sku_a", quantity=100, priority=1),
            OutboundOrder(sku="sku_b", quantity=100, priority=2),
        ],
    ),
]

PRODUCTION_JOBS = [
    ProductionOrder(
        job_id=1,
        output_sku="sku_a",
        quantity=100,
        start_time=0,
        node_name="productionlien",
    ),
    ProductionOrder(
        job_id=2,
        output_sku="sku_b",
        quantity=100,
        start_time=0,
        node_name="productionlien",
    ),
]
