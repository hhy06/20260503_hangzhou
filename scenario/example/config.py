"""Simulation configuration for the simple linear example.

Timeline
--------
t=10    raw_a arrives at raw_wh  (source → raw_wh)
t=20    raw_b arrives at raw_wh  (source → raw_wh)
t=20    prod starts producing fg_x (materials now available)
t=40    fg_x production completes
t=40    prod starts producing fg_y
t=60    fg_y production completes
"""
from scenario.example.sku import N, SKUS, PALLET_SIZE
from scenario.example.bom import FG_BOM
from scenario.example.plant_topology import NODES, EDGES

MANAGEMENT = {
    "type": "static_order",
    "decision_interval": 1.0,
}

SIM_DURATION = 100
