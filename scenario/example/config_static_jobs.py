"""Static orders for the simple linear example.

Timeline
--------
t=10    2×raw_a arrive at raw_wh
t=19    2×raw_b arrive at raw_wh
t=20    prod starts fg_x (consumes 1 raw_a + 1 raw_b, runs 20 min)
t=40    fg_x done → prod starts fg_y (consumes remaining, runs 20 min)
t=60    fg_y done
t=70    FG shipped to sink
"""
from src.infrastructure.edge import TransportOrder
from src.infrastructure.production_node import ProductionOrder

TRANSPORT_ORDERS: list[TransportOrder] = []

TRANSPORT_ORDERS.append(TransportOrder(
    sku="raw_a", quantity=2,
    from_node="source", to_node="raw_wh",
    start_time=10, expect_time=11,
))

# raw_b ships at t=19 so management adds it at t=19,
# the edge delivers it promptly, and production's next
# retry (at t=20) finds both materials ready.
TRANSPORT_ORDERS.append(TransportOrder(
    sku="raw_b", quantity=2,
    from_node="source", to_node="raw_wh",
    start_time=19, expect_time=20,
))

# Move FG to sink after both jobs finish
for sku in ("fg_x", "fg_y"):
    TRANSPORT_ORDERS.append(TransportOrder(
        sku=sku, quantity=1,
        from_node="fg_wh", to_node="sink",
        start_time=70, expect_time=80,
    ))

PRODUCTION_JOBS: list[ProductionOrder] = [
    ProductionOrder(
        order_id=1, sku="fg_x", quantity=1,
        activate_time=0, expect_time=100,
        node_name="prod",
    ),
    ProductionOrder(
        order_id=2, sku="fg_y", quantity=1,
        activate_time=0, expect_time=100,
        node_name="prod",
    ),
]
