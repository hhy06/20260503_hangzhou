"""Day-by-day FG demand for scenario_hangzhou1.

4 SKUs: sku_a, sku_b, sku_c, sku_d.
Each unit requires 4 packages (power/sauce/veg/outer), each taking 1 raw.
Day = 1440 simulation minutes.
"""

DEMAND = {
    1:  {"sku_a": 1280,  "sku_b": 160,  "sku_c": 19140},
    2:  {"sku_a": 1260,  "sku_b": 2290,  "sku_d": 1250},
    3:  {"sku_b": 1270,  "sku_c": 2380,  "sku_d": 1460},
    4:  {"sku_a": 2100, "sku_b": 250,  "sku_c": 460, "sku_d": 70},
    5:  {"sku_a": 1270,  "sku_c": 2100, "sku_d": 150},
    6:  {"sku_a": 1290,  "sku_b": 2280,  "sku_d": 360},
    7:  {"sku_b": 360,  "sku_c": 2370,  "sku_d": 290},
    8:  {"sku_a": 1480,  "sku_b": 2100, "sku_c": 350},
    9:  {"sku_a": 460,  "sku_c": 280,  "sku_d": 100},
    10: {"sku_a": 500, "sku_b": 190,  "sku_c": 270, "sku_d": 1180},
}
