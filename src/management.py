"""Management agent: periodic decision-making component.

The JobManager is a sim.Component agent that wakes every DECISION_INTERVAL
(10 minutes) to issue transport/production orders.  Currently it dispatches
pre-configured static jobs; in the future an AI agent will decide what
orders to issue based on the live simulation state.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import salabim as sim

from src.warehouse_node import OutboundOrder

DECISION_INTERVAL = 10  # minutes between agent wake-ups


@dataclass
class Job:
    time: float
    from_node: str
    to_node: str
    orders: list[OutboundOrder]


class JobManager(sim.Component):
    """A sim.Component agent that issues orders on a periodic wake cycle.

    The agent activates at t=0 and then every *DECISION_INTERVAL* minutes.
    On each wake-up it checks the pre-loaded job queue and issues any jobs
    whose scheduled time has been reached.

    Parameters
    ----------
    jobs : list[Job]
        Pre-configured static jobs (sorted by time on init).
    nodes : Mapping[str, object]
        Node name → node instance map (for issuing outbound orders).
    env : sim.Environment | None
    """

    def __init__(
        self,
        jobs: list[Job],
        nodes: Mapping[str, object],
        env: sim.Environment | None = None,
        **kwargs,
    ):
        self._node_name = "__management__"
        super().__init__(name=self._node_name, env=env, **kwargs)

        self.jobs = sorted(jobs, key=lambda j: j.time)
        self.next_job_idx = 0
        self.nodes = nodes
        self.log: list[dict] = []

    @property
    def node_name(self) -> str:
        return self._node_name

    # ------------------------------------------------------------------
    # SALABIM process: periodic wake cycle
    # ------------------------------------------------------------------

    def process(self):
        """Periodic wake cycle: issue pending orders, then sleep."""
        while True:
            self._issue_pending_jobs()
            yield self.hold(DECISION_INTERVAL)

    # ------------------------------------------------------------------
    # Core issuance logic
    # ------------------------------------------------------------------

    def _issue_pending_jobs(self) -> list[dict]:
        """Issue any jobs whose scheduled time has been reached.

        Returns the list of event dicts issued this cycle (also appended
        to ``self.log``).
        """
        events = []
        while self.next_job_idx < len(self.jobs):
            job = self.jobs[self.next_job_idx]
            if job.time <= self.env.now() + 1e-9:
                node = self.nodes[job.from_node]
                for order in job.orders:
                    node.add_outbound_order(OutboundOrder(
                        sku=order.sku,
                        quantity=order.quantity,
                        priority=order.priority,
                        destination=job.to_node,
                    ))
                event = {
                    "time": job.time,
                    "type": "job_issued",
                    "from": job.from_node,
                    "to": job.to_node,
                    "orders": [(o.sku, o.quantity, o.priority) for o in job.orders],
                }
                events.append(event)
                self.log.append(event)
                self.next_job_idx += 1
            else:
                break
        return events
