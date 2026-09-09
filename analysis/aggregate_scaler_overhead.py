import csv
import json
import math
import statistics
import sys
from pathlib import Path


def pct(values, p):
    xs = sorted(values)
    if not xs:
        return None
    pos = (len(xs) - 1) * p
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def mean_ci95(values):
    xs = [float(x) for x in values if x is not None]
    if not xs:
        return None, None
    m = statistics.mean(xs)
    if len(xs) < 2:
        return m, None
    t95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
           6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
    sd = statistics.stdev(xs)
    ci = t95.get(len(xs)-1, 1.96) * sd / math.sqrt(len(xs))
    return m, ci


root = Path(sys.argv[1])
rows = []
for p in sorted(root.glob("weighted_composition_seed*/scaler_overhead.json")):
    data = json.loads(p.read_text())
    seed = int(p.parent.name.rsplit("seed", 1)[1])
    data["seed"] = seed
    rows.append(data)

if not rows:
    raise SystemExit("No scaler overhead summaries found")

fields = ["seed"] + [k for k in rows[0].keys() if k != "seed"]
with (root / "scaler_overhead_runs.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(sorted(rows, key=lambda r: r["seed"]))

metrics = [
    "worker_replica_seconds_per_request",
    "worker_cpu_request_seconds_per_request",
    "scaler_cpu_request_seconds_per_request",
    "combined_worker_plus_scaler_cpu_request_seconds_per_request",
    "scaler_cpu_m_mean",
    "scaler_cpu_m_p95",
    "scaler_cpu_m_max",
    "scaler_memory_mib_mean",
    "scaler_memory_mib_p95",
    "scaler_memory_mib_max",
    "get_metrics_calls",
    "get_metrics_ms_mean",
    "get_metrics_ms_median",
    "get_metrics_ms_p95",
    "get_metrics_ms_p99",
    "get_metrics_ms_max",
    "sampled_items_mean",
    "sampled_items_max",
    "queue_len_p95",
    "queue_len_max",
]

summary = {"runs": len(rows)}
for metric in metrics:
    values = [r.get(metric) for r in rows if r.get(metric) is not None]
    m, ci = mean_ci95(values)
    summary[f"{metric}_mean_across_runs"] = m
    summary[f"{metric}_ci95"] = ci

all_latency = []
all_cpu = []
all_mem = []
for run_dir in sorted(root.glob("weighted_composition_seed*")):
    log = run_dir / "scaler.log"
    if log.exists():
        for line in log.read_text(errors="replace").splitlines():
            if '"get_metrics_ms"' not in line:
                continue
            try:
                obj = json.loads(line[line.index("{"):line.rindex("}")+1])
                all_latency.append(float(obj["get_metrics_ms"]))
            except Exception:
                pass
    resources = run_dir / "scaler_resources.csv"
    if resources.exists():
        with resources.open() as fh:
            for row in csv.DictReader(fh):
                cpu = row.get("cpu", "")
                mem = row.get("memory", "")
                try:
                    if cpu.endswith("m"):
                        all_cpu.append(float(cpu[:-1]))
                    elif cpu.endswith("u"):
                        all_cpu.append(float(cpu[:-1]) / 1000.0)
                    elif cpu.endswith("n"):
                        all_cpu.append(float(cpu[:-1]) / 1_000_000.0)
                    if mem.endswith("Mi"):
                        all_mem.append(float(mem[:-2]))
                    elif mem.endswith("Gi"):
                        all_mem.append(float(mem[:-2]) * 1024.0)
                    elif mem.endswith("Ki"):
                        all_mem.append(float(mem[:-2]) / 1024.0)
                except ValueError:
                    pass

summary.update({
    "pooled_get_metrics_calls": len(all_latency),
    "pooled_get_metrics_ms_median": statistics.median(all_latency) if all_latency else None,
    "pooled_get_metrics_ms_p95": pct(all_latency, 0.95),
    "pooled_get_metrics_ms_p99": pct(all_latency, 0.99),
    "pooled_get_metrics_ms_max": max(all_latency) if all_latency else None,
    "pooled_scaler_cpu_m_mean": statistics.mean(all_cpu) if all_cpu else None,
    "pooled_scaler_cpu_m_p95": pct(all_cpu, 0.95),
    "pooled_scaler_cpu_m_max": max(all_cpu) if all_cpu else None,
    "pooled_scaler_memory_mib_mean": statistics.mean(all_mem) if all_mem else None,
    "pooled_scaler_memory_mib_p95": pct(all_mem, 0.95),
    "pooled_scaler_memory_mib_max": max(all_mem) if all_mem else None,
})

(root / "scaler_overhead_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
