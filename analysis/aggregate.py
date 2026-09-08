import csv
import json
import math
import re
import sys
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(sys.argv[1])
pattern = re.compile(r"(baseline|semantic)_(steady|composition|volume|mixed)_seed(\d+)$")
SCENARIOS = ["steady", "composition", "volume", "mixed"]
POLICIES = ["baseline", "semantic"]
METRICS = [
    "mean_latency_s",
    "p95_latency_s",
    "p99_latency_s",
    "slo_20s_violation_rate",
    "mean_queue_delay_s",
    "replica_seconds_per_request",
    "max_available_replicas",
]

# Two-sided Student-t critical values for a 95% confidence interval.
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def summarize(values):
    values = [float(v) for v in values]
    n = len(values)
    if n == 0:
        return None, None, None
    m = mean(values)
    if n == 1:
        return m, 0.0, None
    sd = stdev(values)
    tcrit = _T95.get(n - 1, 1.96)
    ci95 = tcrit * sd / math.sqrt(n)
    return m, sd, ci95


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

rows.sort(key=lambda r: (r["scenario"], r["seed"], r["policy"]))
fields = ["policy", "scenario", "seed"] + [
    k for k in rows[0] if k not in {"policy", "scenario", "seed"}
]
with (ROOT / "all_runs.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

aggregate_rows = []
for policy in POLICIES:
    for scenario in SCENARIOS:
        group = [r for r in rows if r["policy"] == policy and r["scenario"] == scenario]
        if not group:
            continue
        out = {"policy": policy, "scenario": scenario, "runs": len(group)}
        for metric in METRICS:
            vals = [r[metric] for r in group if r.get(metric) is not None]
            m, sd, ci95 = summarize(vals)
            out[f"{metric}_mean"] = m
            out[f"{metric}_sd"] = sd
            out[f"{metric}_ci95"] = ci95
        aggregate_rows.append(out)

with (ROOT / "aggregate.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(aggregate_rows[0].keys()))
    w.writeheader()
    w.writerows(aggregate_rows)

# Seeds generate identical arrival traces for baseline and semantic policies, so compare
# policies as paired observations rather than treating them as independent samples.
by_key = {(r["scenario"], r["seed"], r["policy"]): r for r in rows}
paired_rows = []
for scenario in SCENARIOS:
    seeds = sorted({r["seed"] for r in rows if r["scenario"] == scenario})
    for seed in seeds:
        baseline = by_key.get((scenario, seed, "baseline"))
        semantic = by_key.get((scenario, seed, "semantic"))
        if not baseline or not semantic:
            continue
        for metric in METRICS:
            if baseline.get(metric) is None or semantic.get(metric) is None:
                continue
            b = float(baseline[metric])
            s = float(semantic[metric])
            paired_rows.append({
                "scenario": scenario,
                "seed": seed,
                "metric": metric,
                "baseline": b,
                "semantic": s,
                "delta_semantic_minus_baseline": s - b,
                "relative_change_pct": ((s - b) / b * 100.0) if b != 0 else None,
            })

paired_fields = [
    "scenario", "seed", "metric", "baseline", "semantic",
    "delta_semantic_minus_baseline", "relative_change_pct",
]
with (ROOT / "paired_deltas.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=paired_fields)
    w.writeheader()
    w.writerows(paired_rows)

paired_summary = []
for scenario in SCENARIOS:
    for metric in METRICS:
        group = [r for r in paired_rows if r["scenario"] == scenario and r["metric"] == metric]
        if not group:
            continue
        deltas = [r["delta_semantic_minus_baseline"] for r in group]
        rel = [r["relative_change_pct"] for r in group if r["relative_change_pct"] is not None]
        dmean, dsd, dci95 = summarize(deltas)
        rmean, rsd, rci95 = summarize(rel)
        paired_summary.append({
            "scenario": scenario,
            "metric": metric,
            "pairs": len(group),
            "mean_delta_semantic_minus_baseline": dmean,
            "delta_sd": dsd,
            "delta_ci95": dci95,
            "mean_relative_change_pct": rmean,
            "relative_change_sd": rsd,
            "relative_change_ci95": rci95,
        })

with (ROOT / "paired_summary.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(paired_summary[0].keys()))
    w.writeheader()
    w.writerows(paired_summary)

output = {
    "aggregate": aggregate_rows,
    "paired_summary": paired_summary,
}
(ROOT / "aggregate.json").write_text(json.dumps(output, indent=2))
print(json.dumps(output, indent=2))
