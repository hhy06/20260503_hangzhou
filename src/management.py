"""Management layer: issues jobs at different time junctions during simulation."""

from dataclasses import dataclass
from src.warehouse_node import OutboundOrder


@dataclass
class Job:
    time: float
    target_node: str
    orders: list[OutboundOrder]


JOBS = [
    Job(
        time=0,
        target_node="Source",
        orders=[
            OutboundOrder(sku="SKU_A", quantity=500, priority=1),
            OutboundOrder(sku="SKU_B", quantity=200, priority=2),
            OutboundOrder(sku="SKU_C", quantity=1000, priority=3),
        ],
    ),
    Job(
        time=30,
        target_node="Source",
        orders=[
            OutboundOrder(sku="SKU_A", quantity=300, priority=1),
            OutboundOrder(sku="SKU_B", quantity=100, priority=2),
        ],
    ),
    Job(
        time=60,
        target_node="Source",
        orders=[
            OutboundOrder(sku="SKU_C", quantity=500, priority=1),
        ],
    ),
]


class JobManager:
    def __init__(self, jobs: list[Job], env):
        self.jobs = sorted(jobs, key=lambda j: j.time)
        self.env = env
        self.next_job_idx = 0

    def issue_pending_jobs(self, nodes: dict[str, object]) -> list[dict]:
        events = []
        while self.next_job_idx < len(self.jobs):
            job = self.jobs[self.next_job_idx]
            if job.time <= self.env.now() + 1e-9:
                node = nodes[job.target_node]
                for order in job.orders:
                    node.add_outbound_order(OutboundOrder(
                        sku=order.sku,
                        quantity=order.quantity,
                        priority=order.priority,
                    ))
                events.append({
                    "time": job.time,
                    "type": "job_issued",
                    "target": job.target_node,
                    "orders": [(o.sku, o.quantity, o.priority) for o in job.orders],
                })
                self.next_job_idx += 1
            else:
                break
        return events
