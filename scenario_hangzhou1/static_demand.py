"""Day-by-day FG demand for scenario_hangzhou1.

10 days × 3–5 FG SKUs demanded each day.
Day = 1440 simulation minutes.
"""

# {day_index (1-based): {fg_sku: quantity_needed_at_sink}}
DEMAND = {
    1:  {"fg_a1": 120, "fg_a2": 80,  "fg_b1": 60},
    2:  {"fg_a3": 90,  "fg_b2": 130, "fg_b3": 80,  "fg_b4": 70},
    3:  {"fg_a1": 80,  "fg_b1": 100, "fg_a2": 70},
    4:  {"fg_a3": 60,  "fg_b2": 90,  "fg_b3": 110, "fg_a1": 50, "fg_b4": 80},
    5:  {"fg_a2": 110, "fg_b1": 120, "fg_a3": 90},
    6:  {"fg_a1": 130, "fg_b2": 80,  "fg_b3": 100, "fg_b4": 60},
    7:  {"fg_a2": 90,  "fg_b1": 70,  "fg_b3": 140},
    8:  {"fg_a1": 60,  "fg_a3": 100, "fg_b2": 110, "fg_b4": 90},
    9:  {"fg_a3": 80,  "fg_b1": 90,  "fg_b3": 70,  "fg_a2": 60, "fg_b4": 110},
    10: {"fg_a1": 100, "fg_a2": 90,  "fg_b2": 100, "fg_b3": 80},
}
