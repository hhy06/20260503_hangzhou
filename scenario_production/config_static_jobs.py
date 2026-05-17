"""Static job definitions for the production scenario.

Jobs
----
- t=0:    Source -> RawMaterialWH: supply 500 wip_X + 500 wip_Y
- t=15:   Source -> RawMaterialWH: supply 500 wip_X + 500 wip_Y

Production orders
------------------
- t=0:    ProductionLine produces 250 SKU_A (consumes 250 wip_X + 250 wip_Y)
          Expected timeline:
            t=0    consume materials
            t=5    lead_time done
            t=15   output 100 (batch 1)
            t=25   output 100 (batch 2)
            t=30   output 50  (batch 3, partial)

- t=50:   ProductionLine produces 100 SKU_A (consumes 100 wip_X + 100 wip_Y)
"""

from src.warehouse_node import OutboundOrder
from src.management import Job
from src.production_node import ProductionOrder

JOBS = [
    Job(
        time=0,
        from_node="Source",
        to_node="RawMaterialWH",
        orders=[
            OutboundOrder(sku="wip_X", quantity=500, priority=1),
            OutboundOrder(sku="wip_Y", quantity=500, priority=1),
        ],
    ),
    Job(
        time=15,
        from_node="Source",
        to_node="RawMaterialWH",
        orders=[
            OutboundOrder(sku="wip_X", quantity=500, priority=1),
            OutboundOrder(sku="wip_Y", quantity=500, priority=1),
        ],
    ),
]

PRODUCTION_JOBS = [
    ProductionOrder(
        job_id=1,
        output_sku="SKU_A",
        quantity=250,
        start_time=0,
        node_name="ProductionLine",
    ),
    ProductionOrder(
        job_id=2,
        output_sku="SKU_A",
        quantity=100,
        start_time=50,
        node_name="ProductionLine",
    ),
]
