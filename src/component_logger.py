"""Component activity logger — writes detailed activation logs to a text file.

Each time a component is activated (management decision cycle, warehouse dispatch,
production job start), the logger records the component's full state and the
decisions or actions it took.

The log file is overwritten on each new run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.management import JobManager
    from src.warehouse_node import WarehouseNode
    from src.production_node import ProductionNode, ProductionOrder


class ComponentLogger:
    """Writes structured text-format activation logs for simulation components.

    Usage
    -----
        logger = ComponentLogger("simulation_component_log.txt")
        # pass logger to components during construction
        logger.close()       # when simulation is done
    """

    def __init__(self, filepath: str = "simulation_component_log.txt") -> None:
        self.filepath = filepath
        self._fh = open(filepath, "w", encoding="utf-8")
        self._fh.write("=" * 70 + "\n")
        self._fh.write("  SIMULATION COMPONENT ACTIVITY LOG\n")
        self._fh.write(f"  Log file: {filepath}\n")
        self._fh.write("=" * 70 + "\n")
        self._fh.flush()

    def close(self) -> None:
        """Close the log file."""
        if self._fh and not self._fh.closed:
            self._fh.write("\n" + "=" * 70 + "\n")
            self._fh.write("  END OF LOG\n")
            self._fh.write("=" * 70 + "\n")
            self._fh.close()

    def log_management_info(self, manager: JobManager) -> None:
        """Log all information the management component has collected."""
        now = manager.env.now()
        info: dict = getattr(manager, "info", {})

        self._section(f"MANAGEMENT — INFO  t={now:.1f}")

        self._write("  --- Stocks (warehouse inventories) ---\n")
        stock: dict = info.get("stock", {})
        if not stock:
            self._write("    (no stock data)\n")
        else:
            for node_name in sorted(stock):
                items = stock[node_name]
                if not items:
                    continue
                self._write(f"  {node_name}:\n")
                for sku in sorted(items):
                    self._write(f"    {sku}: {items[sku]}\n")

        self._write("\n  --- Received (cumulative at sink) ---\n")
        received: dict = info.get("received", {})
        if received:
            for sku in sorted(received):
                self._write(f"  {sku}: {received[sku]}\n")
        else:
            self._write("    (none)\n")

        self._write("\n  --- Queues ---\n")
        queues: dict = info.get("queues", {})
        any_queue = False
        for node_name in sorted(queues):
            entries = queues[node_name]
            if not entries:
                continue
            any_queue = True
            self._write(f"  {node_name}:\n")
            for entry in entries:
                if "destination" in entry and entry.get("destination") is not None:
                    self._write(
                        f"    [OUTBOUND] sku={entry.get('sku','?')}  "
                        f"qty={entry.get('quantity',0)}  "
                        f"dest={entry.get('destination','?')}  "
                        f"pri={entry.get('priority','?')}\n"
                    )
                elif "job_id" in entry:
                    self._write(
                        f"    [PRODUCTION] job#{entry.get('job_id','?')}  "
                        f"sku={entry.get('output_sku','?')}  "
                        f"qty={entry.get('quantity',0)}  "
                        f"start={entry.get('start_time','?')}\n"
                    )
                elif "status" in entry:
                    self._write(
                        f"    [IN_PROCESS] sku={entry.get('output_sku','?')}  "
                        f"qty={entry.get('quantity',0)}\n"
                    )
        if not any_queue:
            self._write("    (all queues empty)\n")

        self._write("\n  --- BOM / Production Map ---\n")
        producer_for: dict = info.get("producer_for", {})
        if producer_for:
            for out_sku in sorted(producer_for):
                producer = producer_for[out_sku]
                bom = info.get("bom_for", {}).get(out_sku, {})
                inputs = bom.get("inputs", {})
                inputs_str = ", ".join(f"{k} x{v}" for k, v in sorted(inputs.items()))
                self._write(f"  {out_sku} -> {producer}  [{inputs_str}]\n")

            self._write("  Node topology:\n")
            for name in sorted(info.get("upstream_of", {})):
                up = info["upstream_of"][name]
                down = info["downstream_of"][name]
                self._write(f"    {name}: upstream={up}, downstream={down}\n")
        else:
            self._write("    (no production nodes)\n")

        self._write("\n  --- Time Context ---\n")
        day = int(now // manager.DAY) + 1
        self._write(f"  Simulation time: {now:.1f}  (Day {day})\n")
        self._write(f"  Shift starts: {manager.SHIFT_STARTS}\n")
        self._write(f"  Shift duration: {manager.SHIFT_DURATION}\n")

        self._write("\n  --- Demand (pending) ---\n")
        demand: dict = info.get("demand", {})
        current_day = int(now // manager.DAY) + 1
        pending_demand = {d: s for d, s in demand.items() if d <= current_day}
        if pending_demand:
            for day_num in sorted(pending_demand):
                skus = pending_demand[day_num]
                parts = [f"{k} x{v}" for k, v in sorted(skus.items())]
                self._write(f"  Day {day_num}: {', '.join(parts)}\n")
        else:
            self._write("    (no pending demand)\n")

        self._fh.flush()

    def log_management_decisions(self, manager: JobManager) -> None:
        """Log decisions the management just made."""
        now = manager.env.now()
        decisions: list[dict] = getattr(manager, "_decisions_this_cycle", [])

        self._section(f"MANAGEMENT — DECISIONS  t={now:.1f}")

        if not decisions:
            self._write("  (no decisions this cycle)\n")
        else:
            for d in decisions:
                if d["type"] == "issue_job":
                    orders_str = ", ".join(
                        f"{s} x{q}" for s, q in d.get("orders", [])
                    )
                    self._write(
                        f"  ISSUE JOB: {d['from']} -> {d['to']}: {orders_str}\n"
                    )
                elif d["type"] == "transport":
                    self._write(
                        f"  TRANSPORT: {d['from']} -> {d['to']}:  "
                        f"{d['sku']} x{d['qty']}\n"
                    )
                elif d["type"] == "production_order":
                    self._write(
                        f"  PRODUCTION ORDER: node={d['node']}  "
                        f"job#{d['job_id']}  {d['sku']} x{d['qty']}  "
                        f"start={d['start_time']:.1f}\n"
                    )

        self._fh.flush()

    def log_warehouse_activation(
        self,
        node: WarehouseNode,
        dispatched: list[dict[str, Any]] | None = None,
    ) -> None:
        """Log activation state of a warehouse-class node.

        Parameters
        ----------
        node :
            The WarehouseNode being activated.
        dispatched :
            Items dispatched this cycle, each a dict with keys
            ``sku``, ``quantity``, ``destination``.
        """
        now = node.env.now()
        self._section(f"STORAGE NODE: {node.display_name}  t={now:.1f}  Role={node.role.value}")

        if node.role.value == "warehouse":
            self._write("  --- Inventory ---\n")
            if node.inventory:
                for sku in sorted(node.inventory):
                    self._write(f"    {sku}: {node.inventory[sku]}\n")
            else:
                self._write("    (empty)\n")

            pal = node.current_pallets()
            self._write(f"    Capacity: {pal} / {node.node_max_pallets} pallets\n")

        elif node.role.value == "source":
            self._write("  --- Source (infinite supply) ---\n")

        elif node.role.value == "sink":
            self._write("  --- Sink (cumulative received) ---\n")
            if node.received:
                for sku in sorted(node.received):
                    self._write(f"    {sku}: {node.received[sku]}\n")
            else:
                self._write("    (nothing received yet)\n")
            self._fh.flush()
            return

        self._write("\n  --- Output Queue ---\n")
        if node.output_queue:
            for i, order in enumerate(node.output_queue):
                dest = order.destination or "any"
                self._write(
                    f"    Order [{i + 1}]: {order.sku} x{order.quantity}  "
                    f"-> {dest}  (pri={order.priority})\n"
                )
        else:
            self._write("    (empty)\n")

        self._write("\n  --- Dispatch Actions ---\n")
        if dispatched:
            for d in dispatched:
                self._write(
                    f"    Dispatched: {d['sku']} x{d['quantity']} -> {d['destination']}\n"
                )
        else:
            self._write("    (no dispatches this cycle)\n")

        self._fh.flush()

    def log_production_activation(
        self,
        node: ProductionNode,
        job: ProductionOrder | None = None,
    ) -> None:
        """Log activation state of a production node.

        Parameters
        ----------
        node :
            The ProductionNode being activated.
        job :
            The job about to be started, or ``None`` if no eligible job.
        """
        now = node.env.now()
        self._section(f"PRODUCTION NODE: {node.display_name}  t={now:.1f}")

        self._write("  --- Production Queue ---\n")
        if node.production_queue:
            for j in node.production_queue:
                self._write(
                    f"    Job #{j.job_id}: {j.output_sku} x{j.quantity}  "
                    f"(start={j.start_time:.1f})\n"
                )
        else:
            self._write("    (empty)\n")

        self._write("\n  --- In Process ---\n")
        if node._in_process:
            for sku in sorted(node._in_process):
                self._write(f"    {sku}: {node._in_process[sku]}\n")
        else:
            self._write("    (none)\n")

        if job is not None:
            self._write("\n  --- Current Action ---\n")
            self._write(f"    Starting job #{job.job_id}\n")
            self._write(f"    Output: {job.output_sku} x{job.quantity}\n")
            bom_entry = node.bom.get(job.output_sku, {})
            inputs = bom_entry.get("inputs", {})
            if inputs:
                inputs_str = ", ".join(
                    f"{k} x{v * job.quantity}" for k, v in sorted(inputs.items())
                )
                self._write(f"    Required inputs: {inputs_str}\n")
            speed = bom_entry.get("speed", "?")
            lead = bom_entry.get("lead_time", 0)
            self._write(
                f"    BOM: speed={speed} units/min, lead_time={lead} min, "
                f"time_step={node.global_time_step} min\n"
            )
        else:
            self._write("\n  --- Current Action ---\n")
            self._write("    (no eligible job — waiting)\n")

        self._fh.flush()

    def _section(self, title: str) -> None:
        self._fh.write("\n" + "=" * 70 + "\n")
        self._fh.write(f"  {title}\n")
        self._fh.write("=" * 70 + "\n")

    def _write(self, text: str) -> None:
        self._fh.write(text)
