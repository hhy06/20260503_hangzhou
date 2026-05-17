"""Static job definitions for scenario2_test.

Jobs:
  t=0:  Warehouse -> Sink (no stock at t=0, queues but can't ship)
  t=10: Source -> Sink   (supplies the warehouse; auto-forwards to Sink)

This demonstrates delayed delivery: Sink is starved until t=10+.
"""

from src.warehouse_node import OutboundOrder
from src.management import Job

JOBS = [
    Job(
        time=0,
        from_node="Warehouse",
        to_node="Sink",
        orders=[
            OutboundOrder(sku="SKU_X", quantity=100, priority=1),
        ],
    ),
    Job(
        time=10,
        from_node="Source",
        to_node="Warehouse",
        orders=[
            OutboundOrder(sku="SKU_X", quantity=50, priority=1),
        ],
    ),
    Job(
        time=120,
        from_node="Source",
        to_node="Warehouse",
        orders=[
            OutboundOrder(sku="SKU_X", quantity=100, priority=1),
        ],
    ),
]
