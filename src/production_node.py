"""Production node component for SALABIM simulation.

A ProductionNode sits between an upstream warehouse (material source) and a
downstream warehouse (product destination).  It takes raw materials directly
from the upstream warehouse (instant deduction, no transport) and pushes
finished goods to the downstream warehouse.

Production is modelled in batches driven by a global time step::

    batch_output    = min(remaining, production_speed * global_time_step)
    batch_duration  = global_time_step (full) | remaining / speed (partial)
"""

from dataclasses import dataclass, field
from typing import Any

import salabim as sim

from src.warehouse_node import InboundShipment


@dataclass
class ProductionOrder:
    """A production order targeting a specific ProductionNode.

    The order becomes eligible when ``start_time <= env.now()``.  Among
    eligible orders, the one with the lowest ``job_id`` is picked first.
    """
    job_id: int
    output_sku: str
    quantity: int
    start_time: float
    node_name: str                     # which production node to run on
    metadata: dict[str, Any] = field(default_factory=dict)


class ProductionNode(sim.Component):
    """A production line that consumes raw materials and produces finished goods.

    Parameters
    ----------
    name : str
        Node name (also used as SALABIM component name).
    bom : dict
        Bill of materials::

            {output_sku: {
                "inputs":    {input_sku: qty_per_unit, ...},
                "speed":     float,   # output units / minute
                "lead_time": float,   # minutes before first output
            }}

    output_conversion_factors : dict[str, int]
        {output_sku: items_per_pallet} for downstream dispatch.
    upstream_node : WarehouseNode
        The single warehouse this production line draws materials from.
    downstream_node : WarehouseNode
        The single warehouse finished goods are pushed to.
    env : sim.Environment | None
    global_time_step : float
        Simulation-wide production output cycle (minutes).
    """

    def __init__(
        self,
        name: str,
        bom: dict,
        output_conversion_factors: dict[str, int],
        upstream_node,
        downstream_node,
        env: sim.Environment | None = None,
        global_time_step: float = 10.0,
        display_name: str | None = None,
        **kwargs,
    ):
        self._node_name = name
        self.display_name = display_name or name
        super().__init__(name=name, env=env, **kwargs)

        self.bom: dict = bom
        self.output_conversion_factors: dict[str, int] = output_conversion_factors
        self.upstream_node = upstream_node
        self.downstream_node = downstream_node
        self.global_time_step: float = global_time_step

        self.production_queue: list[ProductionOrder] = []
        self.edges_out: list = []
        self.edges_in: list = []
        self.log: list[dict] = []

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def node_name(self) -> str:
        return self._node_name

    def __repr__(self) -> str:
        return self.display_name

    # ------------------------------------------------------------------
    # queue management
    # ------------------------------------------------------------------

    def add_production_order(self, order: ProductionOrder) -> None:
        """Queue a production order (sorted by start_time, then job_id)."""
        self.production_queue.append(order)
        self.production_queue.sort(key=lambda j: (j.start_time, j.job_id))

    def add_edge_out(self, edge) -> None:
        self.edges_out.append(edge)

    def add_edge_in(self, edge) -> None:
        self.edges_in.append(edge)

    # ------------------------------------------------------------------
    # material helpers
    # ------------------------------------------------------------------

    def _check_materials(self, required: dict[str, int]) -> bool:
        """Return True if upstream warehouse has enough of every input SKU."""
        inv = self.upstream_node.inventory
        for sku, needed in required.items():
            if inv.get(sku, 0) < needed:
                return False
        return True

    def _consume_materials(self, required: dict[str, int]) -> None:
        """Deduct materials from upstream warehouse (instant)."""
        inv = self.upstream_node.inventory
        for sku, qty in required.items():
            inv[sku] -= qty
            if inv[sku] <= 0:
                del inv[sku]

    def _output_to_downstream(self, sku: str, quantity: int) -> bool:
        """Push finished goods to downstream warehouse.

        Returns True if accepted.  If ``receive()`` returns False the goods
        are **lost** (no retry, no queue).
        """
        shipment = InboundShipment(sku=sku, quantity=quantity, source=self)
        accepted = self.downstream_node.receive(shipment)

        if accepted:
            self.log.append({
                "time": self.env.now(),
                "type": "production_output",
                "output_sku": sku,
                "quantity": quantity,
                "destination": self.downstream_node.display_name,
            })
        else:
            self.log.append({
                "time": self.env.now(),
                "type": "production_output_lost",
                "output_sku": sku,
                "quantity": quantity,
                "destination": self.downstream_node.display_name,
                "reason": "downstream_full",
            })

        return accepted

    # ------------------------------------------------------------------
    # production execution (generator — yields SALABIM holds)
    # ------------------------------------------------------------------

    def _execute_job(self, job: ProductionOrder):
        """Run a single production order.

        Flow
        ----
        1. Check raw materials availability → fail & return if insufficient.
        2. Consume all required materials instantly.
        3. Wait ``lead_time``.
        4. Loop: produce in ``global_time_step`` batches, push downstream.
        """
        bom_entry = self.bom[job.output_sku]

        # --- 1. material check ---
        required: dict[str, int] = {}
        for input_sku, qty_per in bom_entry["inputs"].items():
            required[input_sku] = qty_per * job.quantity

        if not self._check_materials(required):
            self.log.append({
                "time": self.env.now(),
                "type": "production_failed",
                "job_id": job.job_id,
                "output_sku": job.output_sku,
                "reason": "insufficient_material",
                "required": dict(required),
                "available": {
                    sku: self.upstream_node.inventory.get(sku, 0)
                    for sku in required
                },
            })
            return

        # --- 2. consume ---
        self._consume_materials(required)
        self.log.append({
            "time": self.env.now(),
            "type": "materials_consumed",
            "job_id": job.job_id,
            "output_sku": job.output_sku,
            "quantity": job.quantity,
            "inputs": dict(required),
        })
        self.log.append({
            "time": self.env.now(),
            "type": "production_started",
            "job_id": job.job_id,
            "output_sku": job.output_sku,
            "quantity": job.quantity,
        })

        # --- 3. lead time ---
        lead = bom_entry["lead_time"]
        if lead > 0:
            yield self.hold(lead)

        # --- 4. batch loop ---
        speed: float = bom_entry["speed"]
        remaining: int = job.quantity

        while remaining > 0:
            batch_full = int(speed * self.global_time_step)

            if remaining > batch_full:
                batch = batch_full
                batch_duration = self.global_time_step
            else:
                batch = remaining
                batch_duration = remaining / speed

            yield self.hold(batch_duration)
            self._output_to_downstream(job.output_sku, batch)
            remaining -= batch

        self.log.append({
            "time": self.env.now(),
            "type": "production_completed",
            "job_id": job.job_id,
            "output_sku": job.output_sku,
            "quantity": job.quantity,
        })

    # ------------------------------------------------------------------
    # SALABIM process
    # ------------------------------------------------------------------

    def process(self):
        """SALABIM coroutine: pick eligible jobs and execute them."""
        while True:
            eligible = [
                j for j in self.production_queue
                if j.start_time <= self.env.now() + 1e-9
            ]

            if not eligible:
                yield self.hold(1.0)
                continue

            eligible.sort(key=lambda j: j.job_id)
            job = eligible[0]
            self.production_queue.remove(job)

            yield from self._execute_job(job)
