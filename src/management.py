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
        """Periodic wake cycle: gather info, make decisions, then sleep."""
        while True:
            self.gather_info()
            self.make_decisions()
            yield self.hold(DECISION_INTERVAL)

    # ------------------------------------------------------------------
    # Info collection
    # ------------------------------------------------------------------

    def gather_info(self) -> None:
        """Collect current simulation state into ``self.info``.

        Delegates to ``collect_info()`` which can be overridden by a future
        AI-driven agent for richer state gathering.
        """
        self.info = self.collect_info()

    def collect_info(self) -> dict:
        """Snapshot current node state and pending future demand.

        Returns a dict with keys:
          stock        - {node_name: {sku: qty}} current warehouse inventory
          queues       - {node_name: list} pending outbound orders per node
          future_demand - list of unissued Job objects (time, from, to, orders)
        """
        stock: dict[str, dict[str, int]] = {}
        queues: dict[str, list] = {}
        for name, node in self.nodes.items():
            if hasattr(node, "inventory"):
                stock[name] = dict(node.inventory)
            if hasattr(node, "output_queue"):
                queues[name] = [
                    {"sku": o.sku, "quantity": o.quantity,
                     "priority": o.priority, "destination": o.destination}
                    for o in node.output_queue
                ]
            if hasattr(node, "production_queue"):
                queues.setdefault(name, []).extend([
                    {"job_id": j.job_id, "output_sku": j.output_sku,
                     "quantity": j.quantity, "start_time": j.start_time}
                    for j in node.production_queue
                ])

        future_demand = [
            {"time": j.time, "from": j.from_node, "to": j.to_node,
             "orders": [(o.sku, o.quantity, o.priority) for o in j.orders]}
            for j in self.jobs[self.next_job_idx:]
        ]

        return {
            "stock": stock,
            "queues": queues,
            "future_demand": future_demand,
        }

    # ------------------------------------------------------------------
    # Decision making
    # ------------------------------------------------------------------

    def make_decisions(self) -> None:
        """Issue orders based on current info.

        Current version: issue static jobs whose scheduled time has arrived.
        Future version: an AI agent will decide dynamically using ``self.info``.
        """
        self._issue_pending_jobs()

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
