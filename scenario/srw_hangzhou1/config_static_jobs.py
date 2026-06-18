"""Static orders for rw_hangzhou1.

This scenario uses weigh_safe_stock management, which dynamically
creates production and transport orders. No static orders needed.
"""

from src.infrastructure.edge import TransportOrder
from src.infrastructure.production_node import ProductionOrder

TRANSPORT_ORDERS: list[TransportOrder] = []
PRODUCTION_JOBS: list[ProductionOrder] = []
