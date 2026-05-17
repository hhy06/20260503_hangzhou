from collections.abc import Mapping
from dataclasses import dataclass
from collections import defaultdict

import salabim as sim

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
        **kwargs,
    ):
        self._node_name = "__management__"
        super().__init__(name=self._node_name, env=env, **kwargs)

        self.jobs = sorted(jobs, key=lambda j: j.time)
        self.next_job_idx = 0
        self.nodes = nodes
        self.demand = demand or {}
        self.pallet_sizes = pallet_sizes or {}
        self.log: list[dict] = []

        self._next_job_counter = 1000

    @property
    def node_name(self) -> str:
        return self._node_name

    def process(self):
        while True:
            self._issue_pending_jobs()
            self.gather_info()
            self.make_decisions()
            yield self.hold(DECISION_INTERVAL)

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
        DAY = 1440

        current_day = int(now // DAY) + 1

        fg_need: dict[str, int] = defaultdict(int)
        for day, skus in info["demand"].items():
            if day <= current_day + 1:
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

        if net <= 0:
            if fg_stock > 0 and fg_stock >= required - received:
                self._issue_transport("fg_wh", "sink", sku, fg_stock)
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
        net_prod = self._round_up(sku, net)

        job_id = self._next_job_id()
        prod_node.add_production_order(ProductionOrder(
            job_id=job_id,
            output_sku=sku,
            quantity=net_prod,
            start_time=now,
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
        net_prod = self._round_up(wip_sku, net)

        for input_sku, qty_per in inputs.items():
            needed = qty_per * net_prod
            self._ensure_material_at(input_sku, needed, factory_upstream, info)

        job_id = self._next_job_id()
        prod_node.add_production_order(ProductionOrder(
            job_id=job_id,
            output_sku=wip_sku,
            quantity=net_prod,
            start_time=self.env.now(),
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

    def _round_up(self, sku: str, quantity: int) -> int:
        ps = self.pallet_sizes.get(sku, 1)
        if ps <= 1:
            return quantity
        return ((quantity + ps - 1) // ps) * ps

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
        qty = self._round_up(sku, quantity)
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
                self.next_job_idx += 1
            else:
                break
        return events
