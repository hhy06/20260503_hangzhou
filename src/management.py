from collections.abc import Mapping
from dataclasses import dataclass
from collections import defaultdict

import salabim as sim

from src.component_logger import ComponentLogger
from src.warehouse_node import OutboundOrder
from src.production_node import ProductionOrder

DECISION_INTERVAL = 10
SAFETY_BUFFER = 50


@dataclass
class Job:
    time: float
    from_node: str
    to_node: str
    orders: list[OutboundOrder]


class JobManager(sim.Component):

    def __init__(
        self,
        jobs: list[Job],
        nodes: Mapping[str, object],
        env: sim.Environment | None = None,
        demand: dict | None = None,
        pallet_sizes: dict[str, int] | None = None,
        day_length: int = 1440,
        shift_starts: list[int] | None = None,
        shift_duration: int = 690,
        logger: ComponentLogger | None = None,
        **kwargs,
    ):
        self._node_name = "__management__"
        super().__init__(name=self._node_name, env=env, **kwargs)

        self.jobs = sorted(jobs, key=lambda j: j.time)
        self.next_job_idx = 0
        self.nodes = nodes
        self.demand = demand or {}
        self.pallet_sizes = pallet_sizes or {}
        self.DAY = day_length
        self.SHIFT_STARTS = shift_starts or [480, 1200]
        self.SHIFT_DURATION = shift_duration
        self.log: list[dict] = []
        self._logger = logger
        self._decisions_this_cycle: list[dict] = []

        self._next_job_counter = 1000

    @property
    def node_name(self) -> str:
        return self._node_name

    def process(self):
        while True:
            self._decisions_this_cycle = []
            self._issue_pending_jobs()
            self.gather_info()
            if self._logger is not None:
                self._logger.log_management_info(self)
            self.make_decisions()
            if self._logger is not None:
                self._logger.log_management_decisions(self)
            yield self.hold(DECISION_INTERVAL)

    def _next_shift_start(self, after: float | None = None) -> float:
        if after is None:
            after = self.env.now()
        day_start = (int(after // self.DAY)) * self.DAY
        for ss in self.SHIFT_STARTS:
            t = day_start + ss
            if t >= after - 1e-9:
                return t
        return (int(after // self.DAY) + 1) * self.DAY + self.SHIFT_STARTS[0]

    def _prev_shift_start(self, before: float) -> float:
        day_start = (int(before // self.DAY)) * self.DAY
        for ss in reversed(self.SHIFT_STARTS):
            t = day_start + ss
            if t <= before + 1e-9:
                return t
        return (int(before // self.DAY) - 1) * self.DAY + self.SHIFT_STARTS[-1]

    def gather_info(self) -> None:
        self.info = self.collect_info()

    def collect_info(self) -> dict:
        stock: dict[str, dict[str, int]] = {}
        received: dict[str, int] = {}
        queues: dict[str, list] = {}
        producer_for: dict[str, str] = {}
        bom_for: dict[str, dict] = {}
        upstream_of: dict[str, str] = {}
        downstream_of: dict[str, str] = {}
        supplied_by: dict[str, list[str]] = {}

        for name, node in self.nodes.items():
            if hasattr(node, "inventory"):
                stock[name] = dict(node.inventory)
            if hasattr(node, "received"):
                received.update(dict(node.received))
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
            if hasattr(node, "in_process_quantity"):
                for sku, qty in node.in_process_quantity.items():
                    queues.setdefault(name, []).append({
                        "output_sku": sku, "quantity": qty,
                        "status": "in_process",
                    })
            if hasattr(node, "bom"):
                for out_sku, bom_entry in node.bom.items():
                    producer_for[out_sku] = name
                    bom_for[out_sku] = bom_entry
                upstream_of[name] = node.upstream_node.node_name
                downstream_of[name] = node.downstream_node.node_name
            if hasattr(node, "edges_in"):
                supplied_by[name] = [
                    e.from_node.node_name for e in node.edges_in
                ]

        return {
            "stock": stock,
            "received": received,
            "queues": queues,
            "demand": self.demand,
            "producer_for": producer_for,
            "bom_for": bom_for,
            "upstream_of": upstream_of,
            "downstream_of": downstream_of,
            "supplied_by": supplied_by,
        }

    def make_decisions(self) -> None:
        """Pull-based DRP algorithm.

        Starting from FG demand, works backward through the BOM tree
        to issue transport and production orders as needed.
        """
        info = self.info
        now = self.env.now()

        current_day = int(now // self.DAY) + 1

        fg_need: dict[str, int] = defaultdict(int)
        for day, skus in info["demand"].items():
            if day <= current_day:
                for sku, qty in skus.items():
                    fg_need[sku] += qty

        if not fg_need:
            return

        for sku in sorted(fg_need):
            self._plan_fg_supply(sku, fg_need[sku], now, info)

    def _next_job_id(self) -> int:
        self._next_job_counter += 1
        return self._next_job_counter

    def _find_node(self, name: str):
        return self.nodes.get(name)

    def _qty_in_production_queue(self, sku: str, info: dict) -> int:
        total = 0
        for node_q in info["queues"].values():
            for entry in node_q:
                if entry.get("output_sku") == sku:
                    total += entry["quantity"]
        return total

    def _qty_in_outbound_queue(self, node: str, sku: str, dest: str,
                               info: dict) -> int:
        total = 0
        for entry in info["queues"].get(node, []):
            if entry.get("destination") is None:
                continue
            if entry.get("sku") != sku:
                continue
            if dest is not None and entry.get("destination") != dest:
                continue
            total += entry["quantity"]
        return total

    def _plan_fg_supply(self, sku: str, required: int, now: float,
                        info: dict) -> None:
        received = info["received"].get(sku, 0)
        fg_stock = info["stock"].get("fg_wh", {}).get(sku, 0)
        in_prod = self._qty_in_production_queue(sku, info)
        in_transit = self._qty_in_outbound_queue("fg_wh", sku, "sink", info)

        net = required - received - fg_stock - in_prod - in_transit

        producer_name = info["producer_for"].get(sku)
        upstream_name = info["upstream_of"].get(producer_name, "")
        bom_entry = info["bom_for"].get(sku, {})
        inputs = bom_entry.get("inputs", {})

        total_pending = in_prod + max(0, net)
        if total_pending > 0:
            for input_sku, qty_per in inputs.items():
                needed = qty_per * total_pending
                self._ensure_material_at(input_sku, needed, upstream_name, info)
            # Ensure total raw at the factories' upstream (line_side).
            # Each individual _ensure_material_at above cascades to
            # per-package raw checks that only see one SKU's need at a
            # time.  When line_side stock is low the aggregate factory
            # requirement (4 packages × total_pending) can trigger a
            # raw transport that the individual calls miss.
            total_raw = 0
            raw_node = None
            for input_sku, qty_per in inputs.items():
                pkg_producer = info["producer_for"].get(input_sku)
                if pkg_producer is not None:
                    raw_node = info["upstream_of"].get(pkg_producer, "")
                pkg_bom = info["bom_for"].get(input_sku, {})
                for mat_sku, mat_qty in pkg_bom.get("inputs", {}).items():
                    total_raw += mat_qty * qty_per * total_pending
            if total_raw > 0 and raw_node:
                self._ensure_material_at("raw", total_raw, raw_node, info)

        if net <= 0:
            if fg_stock > 0:
                to_ship = min(fg_stock, required - received)
                if to_ship > 0:
                    self._issue_transport("fg_wh", "sink", sku, to_ship)
            return

        if fg_stock > 0:
            to_ship = min(fg_stock, net)
            self._issue_transport("fg_wh", "sink", sku, to_ship)
            net -= to_ship

        if net <= 0:
            return

        if producer_name is None:
            return
        prod_node = self._find_node(producer_name)

        job_id = self._next_job_id()
        start_time = self._next_shift_start(now)
        prod_node.add_production_order(ProductionOrder(
            job_id=job_id,
            output_sku=sku,
            quantity=net,
            start_time=start_time,
            node_name=producer_name,
        ))
        self.log.append({
            "time": now,
            "type": "production_ordered",
            "job_id": job_id,
            "output_sku": sku,
            "quantity": net,
            "node": producer_name,
        })
        self._decisions_this_cycle.append({
            "type": "production_order",
            "job_id": job_id,
            "sku": sku,
            "qty": net,
            "node": producer_name,
            "start_time": start_time,
        })

    def _incoming_to(self, target_node: str, sku: str, info: dict) -> int:
        total = 0
        for supplier in info.get("supplied_by", {}).get(target_node, []):
            for entry in info["queues"].get(supplier, []):
                if entry.get("destination") == target_node and entry.get("sku") == sku:
                    total += entry["quantity"]
        return total

    def _ensure_material_at(self, sku: str, need: int, target_node: str,
                            info: dict) -> None:
        stock = info["stock"].get(target_node, {}).get(sku, 0)
        in_prod = self._qty_in_production_queue(sku, info)
        in_transit = self._incoming_to(target_node, sku, info)

        deficit = need - stock - in_prod - in_transit
        if deficit <= 0:
            return

        producer_name = info["producer_for"].get(sku)
        if producer_name is not None:
            self._plan_wip_supply(sku, deficit, target_node, producer_name,
                                  info)
            return

        self._pull_one_hop(sku, deficit, target_node, info)

    def _pull_one_hop(self, sku: str, need: int, target_node: str,
                      info: dict) -> None:
        suppliers = info.get("supplied_by", {}).get(target_node, [])
        if not suppliers:
            return
        supplier = suppliers[0]
        supplier_stock = info["stock"].get(supplier, {}).get(sku, 0)
        if supplier_stock < need:
            self._pull_one_hop(sku, need - supplier_stock, supplier, info)
        self._issue_transport(supplier, target_node, sku, need)

    def _plan_wip_supply(self, wip_sku: str, need: int, target_wh: str,
                         producer_name: str, info: dict) -> None:
        wip_stock = info["stock"].get("semi_wh", {}).get(wip_sku, 0)

        # `need` is the deficit from _ensure_material_at, which already
        # subtracted in_prod.  Only wip_stock (at semi_wh) is new here.
        net = need - wip_stock
        if net <= 0:
            if wip_stock > 0:
                to_pull = min(need, wip_stock)
                self._pull_one_hop(wip_sku, to_pull, target_wh, info)
            return

        if wip_stock > 0:
            self._pull_one_hop(wip_sku, wip_stock, target_wh, info)

        prod_node = self._find_node(producer_name)
        bom_entry = info["bom_for"].get(wip_sku, {})
        inputs = bom_entry.get("inputs", {})
        factory_upstream = info["upstream_of"].get(producer_name, "")

        for input_sku, qty_per in inputs.items():
            needed = qty_per * net
            self._ensure_material_at(input_sku, needed, factory_upstream, info)

        job_id = self._next_job_id()
        start_time = self._next_shift_start(self.env.now())
        prod_node.add_production_order(ProductionOrder(
            job_id=job_id,
            output_sku=wip_sku,
            quantity=net,
            start_time=start_time,
            node_name=producer_name,
        ))
        self.log.append({
            "time": self.env.now(),
            "type": "production_ordered",
            "job_id": job_id,
            "output_sku": wip_sku,
            "quantity": net,
            "node": producer_name,
        })
        self._decisions_this_cycle.append({
            "type": "production_order",
            "job_id": job_id,
            "sku": wip_sku,
            "qty": net,
            "node": producer_name,
            "start_time": start_time,
        })


    def _pending_transport(self, from_node: str, sku: str, dest: str,
                           info: dict) -> int:
        total = 0
        for entry in info["queues"].get(from_node, []):
            if entry.get("destination") == dest and entry.get("sku") == sku:
                total += entry["quantity"]
        return total

    def _issue_transport(self, from_node: str, to_node: str,
                         sku: str, quantity: int) -> None:
        node = self._find_node(from_node)
        if node is None:
            return
        qty = quantity
        if qty <= 0:
            return
        already = self._pending_transport(from_node, sku, to_node, self.info)
        qty -= already
        if qty <= 0:
            return
        node.add_outbound_order(OutboundOrder(
            sku=sku,
            quantity=qty,
            priority=1,
            destination=to_node,
        ))
        self._decisions_this_cycle.append({
            "type": "transport",
            "from": from_node,
            "to": to_node,
            "sku": sku,
            "qty": qty,
        })

    def _issue_pending_jobs(self) -> list[dict]:
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
                    "orders": [(o.sku, o.quantity, o.priority)
                               for o in job.orders],
                }
                events.append(event)
                self.log.append(event)
                self._decisions_this_cycle.append({
                    "type": "issue_job",
                    "from": job.from_node,
                    "to": job.to_node,
                    "orders": [(o.sku, o.quantity) for o in job.orders],
                })
                self.next_job_idx += 1
            else:
                break
        return events
