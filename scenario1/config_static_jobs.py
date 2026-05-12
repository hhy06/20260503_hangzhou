"""Static job definitions for scenario1."""

from src.warehouse_node import OutboundOrder
from src.management import Job

JOBS = [
    Job(
        time=0,
        from_node="Source",
        to_node="Sink",
        orders=[
            OutboundOrder(sku="SKU_A", quantity=500, priority=1),
            OutboundOrder(sku="SKU_B", quantity=200, priority=2),
            OutboundOrder(sku="SKU_C", quantity=1000, priority=3),
        ],
    ),
    Job(
        time=30,
        from_node="Source",
        to_node="Sink",
        orders=[
            OutboundOrder(sku="SKU_A", quantity=300, priority=1),
            OutboundOrder(sku="SKU_B", quantity=100, priority=2),
        ],
    ),
    Job(
        time=60,
        from_node="Source",
        to_node="Sink",
        orders=[
            OutboundOrder(sku="SKU_C", quantity=500, priority=1),
        ],
    ),
    Job(
        time=80,
        from_node="Source",
        to_node="Sink",
        orders=[
            OutboundOrder(sku="SKU_A", quantity=200, priority=1),
        ],
    ),
]
