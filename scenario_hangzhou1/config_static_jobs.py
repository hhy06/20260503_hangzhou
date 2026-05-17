from src.warehouse_node import OutboundOrder
from src.management import Job

JOBS = [
    Job(time=0, from_node="source", to_node="raw_wh",
        orders=[OutboundOrder(sku="raw", quantity=2000, priority=1)]),
    Job(time=0, from_node="raw_wh", to_node="line_side",
        orders=[OutboundOrder(sku="raw", quantity=1000, priority=1)]),
]

PRODUCTION_JOBS = []
