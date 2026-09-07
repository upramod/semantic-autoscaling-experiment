import csv
import json
import re
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(sys.argv[1])
pattern = re.compile(r"(baseline|semantic)_(steady|composition|volume|mixed)_seed(\d+)$")
rows = []
for d in sorted(ROOT.iterdir()):
    if not d.is_dir():
        continue
    m = pattern.match(d.name)
    if not m or not (d / "summary.json").exists():
        continue
    data = json.loads((d / "summary.json").read_text())
    data.update(policy=m.group(1), scenario=m.group(2), seed=int(m.group(3)))
    rows.append(data)

if not rows:
    print("No completed runs found")
    raise SystemExit(0)

fields = ["policy", "scenario", "seed"] + [k for k in rows[0] if k not in {"policy", "scenario", "seed"}]
with (ROOT / "all_runs.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader(); w.writerows(rows)

metrics = ["p95_latency_s", "p99_latency_s", "slo_20s_violation_rate", "replica_seconds_per_request", "max_available_replicas"]
agg = []
for policy in ["baseline", "semantic"]:
    for scenario in ["steady", "composition", "volume", "mixed"]:
        group = [r for r in rows if r["policy"] == policy and r["scenario"] == scenario]
        if not group:
            continue
        row = {"policy": policy, "scenario": scenario, "runs": len(group)}
        for metric in metrics:
            vals = [float(r[metric]) for r in group if r.get(metric) is not None]
            row[metric] = mean(vals) if vals else None
        agg.append(row)

with (ROOT / "aggregate.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(agg[0].keys()))
    w.writeheader(); w.writerows(agg)
print(json.dumps(agg, indent=2))
