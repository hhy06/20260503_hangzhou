"""Management layer: issues jobs at scheduled times during simulation.

The JobManager reads a list of Jobs (provided by the scenario layer)
and injects outbound orders into warehouse nodes as simulation time advances.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from src.warehouse_node import OutboundOrder


@dataclass
class Job:
    time: float
    from_node: str
    to_node: str
    orders: list[OutboundOrder]


class JobManager:
    """Holds a sorted list of Jobs and releases them to the node graph as simulation time
    advances.  Called from the main simulation loop."""

    def __init__(self, jobs: list[Job], env):
        self.jobs = sorted(jobs, key=lambda j: j.time)
        self.env = env
        self.next_job_idx = 0

    def issue_pending_jobs(self, nodes: Mapping[str, object]) -> list[dict]:
        events = []
        while self.next_job_idx < len(self.jobs):
            job = self.jobs[self.next_job_idx]
            if job.time <= self.env.now() + 1e-9:
                node = nodes[job.from_node]
                for order in job.orders:
                    node.add_outbound_order(OutboundOrder(
                        sku=order.sku,
                        quantity=order.quantity,
                        priority=order.priority,
                        destination=job.to_node,
                    ))
                events.append({
                    "time": job.time,
                    "type": "job_issued",
                    "from": job.from_node,
                    "to": job.to_node,
                    "orders": [(o.sku, o.quantity, o.priority) for o in job.orders],
                })
                self.next_job_idx += 1
            else:
                break
        return events
