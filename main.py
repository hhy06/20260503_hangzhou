"""Example simulation with warehouse nodes and edges."""

import salabim as sim

from src.edge import Edge, TransferMode
from src.warehouse_node import WarehouseNode, OutboundOrder, InboundShipment


def print_state(warehouse: WarehouseNode):
    print(f"  {warehouse.node_name}: pallets={warehouse.current_pallets()}/{warehouse.node_max_pallets}")
    for sku, qty in sorted(warehouse.inventory.items()):
        print(f"    {sku}: {qty} items ({warehouse.pallets_for_quantity(sku, qty)} pallets)")


def run_example():
    sim.yieldless(False)
    env = sim.Environment(trace=False)

    warehouse_a = WarehouseNode(
        name="WarehouseA",
        max_pallets=100,
        conversion_factors={"SKU_A": 50, "SKU_B": 20, "SKU_C": 100},
        env=env,
        dispatch_interval=5,
        dispatch_max_pallets=3,
    )

    warehouse_b = WarehouseNode(
        name="WarehouseB",
        max_pallets=80,
        conversion_factors={"SKU_A": 50, "SKU_B": 20, "SKU_C": 100},
        env=env,
        dispatch_interval=5,
        dispatch_max_pallets=2,
    )

    edge_a_b = Edge(
        from_node=warehouse_a,
        to_node=warehouse_b,
        transfer_mode=TransferMode.BATCH,
        transfer_time=10,
        batch_size=5,
    )
    warehouse_a.add_edge_out(edge_a_b)
    warehouse_b.add_edge_in(edge_a_b)

    warehouse_a.inventory = {"SKU_A": 200, "SKU_B": 100, "SKU_C": 500}

    warehouse_a.add_outbound_order(OutboundOrder(sku="SKU_A", quantity=100, priority=1))
    warehouse_a.add_outbound_order(OutboundOrder(sku="SKU_B", quantity=60, priority=2))
    warehouse_a.add_outbound_order(OutboundOrder(sku="SKU_C", quantity=300, priority=3))

    print("Initial state:")
    print_state(warehouse_a)

    print("\nOutput queue:")
    for order in warehouse_a.output_queue:
        print(f"  {order.sku}: qty={order.quantity}, priority={order.priority}")

    print("\n--- Simulation starts ---")

    last_pallets = warehouse_a.current_pallets()
    while env.now() < 30:
        env.run(env.now() + 5)
        current_pallets = warehouse_a.current_pallets()
        if current_pallets != last_pallets:
            print(f"  t={env.now():.1f}: dispatched, remaining pallets={current_pallets}/{warehouse_a.node_max_pallets}")
            print("  Inventory:")
            for sku, qty in sorted(warehouse_a.inventory.items()):
                print(f"    {sku}: {qty} items")
            last_pallets = current_pallets

    print("\n--- Final state ---")
    print_state(warehouse_a)
    print_state(warehouse_b)

    print(f"\nEdge transfer test:")
    print(f"  {edge_a_b.name}:")
    print(f"    3 pallets via batch mode: {edge_a_b.transfer_duration(3)} time units")
    print(f"    5 pallets via batch mode: {edge_a_b.transfer_duration(5)} time units")
    print(f"    6 pallets via batch mode: {edge_a_b.transfer_duration(6)} time units")

    edge_per_pallet = Edge(
        from_node=warehouse_a,
        to_node=warehouse_b,
        transfer_mode=TransferMode.PER_PALLET,
        transfer_time=2,
    )
    print(f"\n  Per-pallet edge: {edge_per_pallet.transfer_duration(3)} time units for 3 pallets")


if __name__ == "__main__":
    run_example()
