#!/usr/bin/env python3

import json
import sys
from collections import Counter
from pathlib import Path
import pandas as pd

jsonl_file = sys.argv[1] if len(sys.argv) > 1 else "sim.jsonl"

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

        subject = event.get("subject", event.get("node", "<missing>"))
        event_type = event.get("type", "<missing>")

        counts[(subject, event_type)] += 1

# Convert to table
rows = [
    {"subject": subject, "type": event_type, "count": count}
    for (subject, event_type), count in counts.items()
]

df = pd.DataFrame(rows)

table = (
    df.pivot(
        index="subject",
        columns="type",
        values="count"
    )
    .fillna(0)
    .astype(int)
)


# Total per subject (row sum)
table["TOTAL"] = table.sum(axis=1)

# Total per type (column sum)
table.loc["TOTAL"] = table.sum(axis=0)

# Sort subjects by total count (keep TOTAL row at bottom)
total_row = table.loc["TOTAL"]
table = table.drop(index="TOTAL")
table = table.sort_values("TOTAL", ascending=False)
table.loc["TOTAL"] = total_row

print(table)


out_csv = Path(jsonl_file).parent / "subject_type_counts.csv"
table.to_csv(out_csv)
