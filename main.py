"""Main simulation entry point: builds system from config, runs with management."""

import salabim as sim

from src.config import SKUS, PALLET_SIZE, NODES, EDGES, SIM_DURATION
from src.edge import Edge
from src.warehouse_node import WarehouseNode, SourceNode, SinkNode
from src.management import JobManager, JOBS


def build_nodes(env: sim.Environment) -> dict[str, object]:
    nodes = {}
    for node_name, cfg in NODES.items():
        cf = dict(PALLET_SIZE)
        node_type = cfg["type"]

        if node_type == "source":
            node = SourceNode(
                name=node_name,
                conversion_factors=cf,
                env=env,
                dispatch_interval=cfg["dispatch_interval"],
                dispatch_max_pallets=cfg["dispatch_max_pallets"],
            )
        elif node_type == "sink":
            node = SinkNode(
                name=node_name,
                conversion_factors=cf,
                env=env,
            )
        else:
            node = WarehouseNode(
                name=node_name,
                max_pallets=cfg["max_pallets"],
                conversion_factors=cf,
                env=env,
                dispatch_interval=cfg["dispatch_interval"],
                dispatch_max_pallets=cfg["dispatch_max_pallets"],
            )
        nodes[node_name] = node
    return nodes


def build_edges(nodes: dict[str, object]) -> list[Edge]:
    edges = []
    for ecfg in EDGES:
        from_node = nodes[ecfg["from_node"]]
        to_node = nodes[ecfg["to_node"]]
        edge = Edge(
            from_node=from_node,
            to_node=to_node,
            transfer_mode=ecfg["transfer_mode"],
            transfer_time=ecfg["transfer_time"],
            batch_size=ecfg.get("batch_size", 1),
        )
        from_node.add_edge_out(edge)
        to_node.add_edge_in(edge)
        edges.append(edge)
    return edges


def run_simulation():
    sim.yieldless(False)
    env = sim.Environment(trace=False)

    nodes = build_nodes(env)
    edges = build_edges(nodes)
    job_manager = JobManager(JOBS, env)

    print("=" * 70)
    print("SIMULATION CONFIGURATION")
    print("=" * 70)
    print(f"SKUs: {SKUS}")
    print(f"Pallet sizes: {PALLET_SIZE}")
    print()
    print("Nodes:")
    for name, cfg in NODES.items():
        print(f"  {name}: type={cfg['type']}, max_pallets={cfg.get('max_pallets', 'inf')}")
    print()
    print("Edges:")
    for e in edges:
        print(f"  {e.name} | mode={e.transfer_mode.value}, time={e.transfer_time}, batch={e.batch_size}")
    print()
    print("Jobs:")
    for j in JOBS:
        print(f"  t={j.time}: issue to {j.target_node} -> {[(o.sku, o.quantity) for o in j.orders]}")
    print("=" * 70)
    print()

    def process_events_at(t):
        events = job_manager.issue_pending_jobs(nodes)
        for ev in events:
            print(f"  [t={ev['time']:.1f}] JOB ISSUED to {ev['target']}:")
            for sku, qty, pri in ev["orders"]:
                print(f"    -> Order: {sku} x{qty} (priority={pri})")
        for name, node in nodes.items():
            new_logs = [l for l in node.log if l["time"] == t]
            for entry in new_logs:
                if entry["type"] == "order_added":
                    print(f"  [t={entry['time']:.1f}] {name}: order queued -> {entry['sku']} x{entry['quantity']} (pri={entry['priority']})")
                elif entry["type"] == "dispatched":
                    items_str = ", ".join(f"{sku}x{qty}" for sku, qty in entry["items"])
                    print(f"  [t={entry['time']:.1f}] {name}: dispatched -> {items_str}")
                elif entry["type"] == "received":
                    print(f"  [t={entry['time']:.1f}] {name}: received {entry['sku']} x{entry['quantity']} from {entry['source']}")

    def print_state_snapshot(t):
        print(f"\n  [t={t:.1f}] === State snapshot ===")
        for name, node in nodes.items():
            if hasattr(node, 'received'):
                print(f"    {name}: received_total={dict(sorted(node.received.items()))}")
            elif hasattr(node, 'inventory'):
                pallets = node.current_pallets()
                max_p = node.node_max_pallets
                print(f"    {name}: {pallets}/{max_p} pallets | inventory={dict(sorted(node.inventory.items()))}")
        print()

    step = 1
    process_events_at(0)
    while env.now() < SIM_DURATION:
        next_t = min(env.now() + step, SIM_DURATION)
        env.run(next_t)
        process_events_at(env.now())

        if env.now() % 20 == 0:
            print_state_snapshot(env.now())

    print("=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)
    for name, node in nodes.items():
        if hasattr(node, 'received'):
            print(f"  {name} final: {node.received}")
        elif hasattr(node, 'inventory'):
            print(f"  {name} final inventory: {node.inventory}")


if __name__ == "__main__":
    run_simulation()
