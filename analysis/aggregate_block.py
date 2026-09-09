import csv
import json
import math
import re
import sys
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(sys.argv[1])
PATTERN = re.compile(r"(baseline|weighted|cpu50|cpu70|cpu90)_(steady|composition|volume|mixed)_seed(\d+)$")
POLICIES = ["baseline", "weighted", "cpu50", "cpu70", "cpu90"]
SCENARIOS = ["steady", "composition", "volume", "mixed"]
PRIMARY_SCENARIOS = {"steady", "composition", "volume"}
METRICS = [
    "mean_latency_s",
    "p95_latency_s",
    "p99_latency_s",
    "slo_20s_violation_rate",
    "mean_queue_delay_s",
    "replica_seconds_per_request",
    "max_desired_replicas",
    "max_available_replicas",
    "scaling_actions",
    "scale_up_events",
    "scale_down_events",
    "scaling_direction_reversals",
    "first_scale_up_after_burst_s",
    "recovery_to_preburst_s",
]
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def summarize(values):
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None, None, None
    m = mean(vals)
    if len(vals) == 1:
        return m, 0.0, None
    sd = stdev(vals)
    ci = _T95.get(len(vals) - 1, 1.96) * sd / math.sqrt(len(vals))
    return m, sd, ci


def is_dominated(point, others, x_key, y_key):
    x = point[x_key]
    y = point[y_key]
    if x is None or y is None:
        return None
    for other in others:
        ox = other[x_key]
        oy = other[y_key]
        if ox is None or oy is None:
            continue
        if ox <= x and oy <= y and (ox < x or oy < y):
            return True
    return False


rows = []
for d in sorted(ROOT.iterdir()):
    if not d.is_dir():
        continue
    m = PATTERN.match(d.name)
    if not m or not (d / "summary.json").exists():
        continue
    data = json.loads((d / "summary.json").read_text())
    data.update(policy=m.group(1), scenario=m.group(2), seed=int(m.group(3)))
    rows.append(data)

if not rows:
    raise SystemExit("No completed blocked-validation runs found")

rows.sort(key=lambda r: (r["scenario"], r["seed"], POLICIES.index(r["policy"])))
all_fields = ["policy", "scenario", "seed"] + [
    k for k in rows[0] if k not in {"policy", "scenario", "seed"}
]
with (ROOT / "all_runs.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=all_fields)
    w.writeheader()
    w.writerows(rows)

aggregate = []
for scenario in SCENARIOS:
    for policy in POLICIES:
        group = [r for r in rows if r["scenario"] == scenario and r["policy"] == policy]
        if not group:
            continue
        out = {
            "scenario": scenario,
            "policy": policy,
            "runs": len(group),
            "completed_requests": sum(int(r.get("completed", 0)) for r in group),
        }
        for metric in METRICS:
            m, sd, ci = summarize([r.get(metric) for r in group])
            out[f"{metric}_mean"] = m
            out[f"{metric}_sd"] = sd
            out[f"{metric}_ci95"] = ci
        aggregate.append(out)

with (ROOT / "aggregate.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(aggregate[0].keys()))
    w.writeheader()
    w.writerows(aggregate)

# Each scenario/seed is one host block. All five policies run on that same host,
# with cluster recreation and counterbalanced treatment order. Paired differences
# therefore remove host-block effects rather than pairing across different runners.
by_key = {(r["scenario"], r["seed"], r["policy"]): r for r in rows}
comparisons = [("weighted", p) for p in ["baseline", "cpu50", "cpu70", "cpu90"]]
paired = []
for scenario in SCENARIOS:
    seeds = sorted({r["seed"] for r in rows if r["scenario"] == scenario})
    for left, right in comparisons:
        for seed in seeds:
            a = by_key.get((scenario, seed, left))
            b = by_key.get((scenario, seed, right))
            if not a or not b:
                continue
            for metric in METRICS:
                if a.get(metric) is None or b.get(metric) is None:
                    continue
                av = float(a[metric])
                bv = float(b[metric])
                paired.append({
                    "scenario": scenario,
                    "seed": seed,
                    "metric": metric,
                    "left_policy": left,
                    "right_policy": right,
                    "left": av,
                    "right": bv,
                    "delta_left_minus_right": av - bv,
                    "relative_change_pct": ((av - bv) / bv * 100.0) if bv != 0 else None,
                })

paired_fields = [
    "scenario", "seed", "metric", "left_policy", "right_policy",
    "left", "right", "delta_left_minus_right", "relative_change_pct",
]
with (ROOT / "paired_deltas.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=paired_fields)
    w.writeheader()
    w.writerows(paired)

paired_summary = []
for scenario in SCENARIOS:
    for left, right in comparisons:
        for metric in METRICS:
            group = [
                r for r in paired
                if r["scenario"] == scenario and r["metric"] == metric
                and r["left_policy"] == left and r["right_policy"] == right
            ]
            if not group:
                continue
            dmean, dsd, dci = summarize([r["delta_left_minus_right"] for r in group])
            rmean, rsd, rci = summarize([r["relative_change_pct"] for r in group])
            paired_summary.append({
                "scenario": scenario,
                "metric": metric,
                "left_policy": left,
                "right_policy": right,
                "pairs": len(group),
                "mean_delta_left_minus_right": dmean,
                "delta_sd": dsd,
                "delta_ci95": dci,
                "mean_relative_change_pct": rmean,
                "relative_change_sd": rsd,
                "relative_change_ci95": rci,
            })

with (ROOT / "paired_summary.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(paired_summary[0].keys()))
    w.writeheader()
    w.writerows(paired_summary)

# CPU-target sensitivity and operational frontier. A policy is Pareto-efficient when
# no other tested policy has both lower tail/SLO metric and lower replica cost.
frontier = []
for scenario in SCENARIOS:
    points = []
    for row in aggregate:
        if row["scenario"] != scenario:
            continue
        points.append({
            "scenario": scenario,
            "policy": row["policy"],
            "primary_scenario": scenario in PRIMARY_SCENARIOS,
            "p95_latency_s": row.get("p95_latency_s_mean"),
            "slo_20s_violation_rate": row.get("slo_20s_violation_rate_mean"),
            "replica_seconds_per_request": row.get("replica_seconds_per_request_mean"),
        })
    for point in points:
        others = [x for x in points if x["policy"] != point["policy"]]
        dom_p95 = is_dominated(point, others, "p95_latency_s", "replica_seconds_per_request")
        dom_slo = is_dominated(point, others, "slo_20s_violation_rate", "replica_seconds_per_request")
        point["pareto_p95_cost"] = None if dom_p95 is None else not dom_p95
        point["pareto_slo_cost"] = None if dom_slo is None else not dom_slo
        frontier.append(point)

with (ROOT / "frontier.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(frontier[0].keys()))
    w.writeheader()
    w.writerows(frontier)

output = {
    "design": {
        "block": "scenario x seed host",
        "policies": POLICIES,
        "seeds_per_scenario": sorted({r["seed"] for r in rows}),
        "primary_scenarios": sorted(PRIMARY_SCENARIOS),
        "mixed_role": "capacity-limit analysis",
    },
    "completed_requests": sum(int(r.get("completed", 0)) for r in rows),
    "completed_runs": len(rows),
    "aggregate": aggregate,
    "paired_summary": paired_summary,
    "frontier": frontier,
}
(ROOT / "aggregate.json").write_text(json.dumps(output, indent=2))
print(json.dumps(output, indent=2))
