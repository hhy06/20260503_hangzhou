from src.warehouse_node import OutboundOrder
from src.management import Job

JOBS = [
    Job(time=0, from_node="source", to_node="raw_wh",
        orders=[OutboundOrder(sku="raw", quantity=5000, priority=1)]),
]

PRODUCTION_JOBS = []
