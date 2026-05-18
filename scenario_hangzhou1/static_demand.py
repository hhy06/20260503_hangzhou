"""Day-by-day FG demand for scenario_hangzhou1.

4 SKUs: sku_a, sku_b, sku_c, sku_d.
Each unit requires 4 packages (power/sauce/veg/outer), each taking 1 raw.
Day = 1440 simulation minutes.
"""

DEMAND = {
    1:  {"sku_a": 80,  "sku_b": 60,  "sku_c": 40},
    2:  {"sku_a": 60,  "sku_b": 90,  "sku_d": 50},
    3:  {"sku_b": 70,  "sku_c": 80,  "sku_d": 60},
    4:  {"sku_a": 100, "sku_b": 50,  "sku_c": 60, "sku_d": 70},
    5:  {"sku_a": 70,  "sku_c": 100, "sku_d": 50},
    6:  {"sku_a": 90,  "sku_b": 80,  "sku_d": 60},
    7:  {"sku_b": 60,  "sku_c": 70,  "sku_d": 90},
    8:  {"sku_a": 80,  "sku_b": 100, "sku_c": 50},
    9:  {"sku_a": 60,  "sku_c": 80,  "sku_d": 100},
    10: {"sku_a": 100, "sku_b": 90,  "sku_c": 70, "sku_d": 80},
}
