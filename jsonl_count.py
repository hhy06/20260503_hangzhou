#!/usr/bin/env python3

import json
from collections import Counter
import pandas as pd

jsonl_file = "sim.jsonl"

# Count occurrences of (node, type)
counts = Counter()

with open(jsonl_file, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        node = event.get("node", "<missing>")
        event_type = event.get("type", "<missing>")

        counts[(node, event_type)] += 1

# Convert to table
rows = [
    {"node": node, "type": event_type, "count": count}
    for (node, event_type), count in counts.items()
]

df = pd.DataFrame(rows)

table = (
    df.pivot(
        index="node",
        columns="type",
        values="count"
    )
    .fillna(0)
    .astype(int)
)
 


# Total per node (row sum)
table["TOTAL"] = table.sum(axis=1)

# Total per type (column sum)
table.loc["TOTAL"] = table.sum(axis=0)

# Sort nodes by total count (keep TOTAL row at bottom)
total_row = table.loc["TOTAL"]
table = table.drop(index="TOTAL")
table = table.sort_values("TOTAL", ascending=False)
table.loc["TOTAL"] = total_row

print(table)


# Optional export
table.to_csv("node_type_counts.csv")
