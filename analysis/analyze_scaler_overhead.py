import csv
import json
import math
import re
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


def cpu_to_millicores(text):
    text = text.strip()
    if text.endswith("n"):
        return float(text[:-1]) / 1_000_000.0
    if text.endswith("u"):
        return float(text[:-1]) / 1_000.0
    if text.endswith("m"):
        return float(text[:-1])
    return float(text) * 1000.0


def memory_to_mib(text):
    text = text.strip()
    units = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
        "Ti": 1024 * 1024,
        "K": 1000 / (1024 * 1024),
        "M": 1_000_000 / (1024 * 1024),
        "G": 1_000_000_000 / (1024 * 1024),
    }
    for unit, factor in units.items():
        if text.endswith(unit):
            return float(text[:-len(unit)]) * factor
    return float(text) / (1024 * 1024)


def main():
    run_dir = Path(sys.argv[1])
    resource_csv = Path(sys.argv[2])
    scaler_log = Path(sys.argv[3])

    summary = json.loads((run_dir / "summary.json").read_text())
    completed = int(summary["completed"])
    duration_s = float(summary.get("observed_arrival_duration_s") or 600.0)

    cpu_m = []
    mem_mib = []
    with resource_csv.open() as fh:
        for row in csv.DictReader(fh):
            try:
                cpu_m.append(cpu_to_millicores(row["cpu"]))
                mem_mib.append(memory_to_mib(row["memory"]))
            except (ValueError, KeyError):
                continue

    metric_ms = []
    sampled = []
    queue_len = []
    for line in scaler_log.read_text(errors="replace").splitlines():
        m = re.search(r'(\{.*"get_metrics_ms".*\})', line)
        if not m:
            continue
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        metric_ms.append(float(obj["get_metrics_ms"]))
        sampled.append(int(obj.get("sampled_items", 0)))
        queue_len.append(int(obj.get("queue_len", 0)))

    worker_replica_s_per_request = float(summary["replica_seconds_per_request"])
    worker_cpu_request_cores = 0.250
    scaler_cpu_request_cores = 0.100
    scaler_memory_request_mib = 96.0
    scaler_cpu_request_seconds_per_request = (
        scaler_cpu_request_cores * duration_s / completed if completed else None
    )
    worker_cpu_request_seconds_per_request = worker_cpu_request_cores * worker_replica_s_per_request
    combined_cpu_request_seconds_per_request = (
        worker_cpu_request_seconds_per_request + scaler_cpu_request_seconds_per_request
        if scaler_cpu_request_seconds_per_request is not None else None
    )

    out = {
        "completed": completed,
        "duration_s": duration_s,
        "worker_replica_seconds_per_request": worker_replica_s_per_request,
        "worker_cpu_request_seconds_per_request": worker_cpu_request_seconds_per_request,
        "scaler_cpu_request_cores": scaler_cpu_request_cores,
        "scaler_memory_request_mib": scaler_memory_request_mib,
        "scaler_cpu_request_seconds_per_request": scaler_cpu_request_seconds_per_request,
        "combined_worker_plus_scaler_cpu_request_seconds_per_request": combined_cpu_request_seconds_per_request,
        "resource_samples": len(cpu_m),
        "scaler_cpu_m_mean": statistics.mean(cpu_m) if cpu_m else None,
        "scaler_cpu_m_p95": pct(cpu_m, 0.95),
        "scaler_cpu_m_max": max(cpu_m) if cpu_m else None,
        "scaler_memory_mib_mean": statistics.mean(mem_mib) if mem_mib else None,
        "scaler_memory_mib_p95": pct(mem_mib, 0.95),
        "scaler_memory_mib_max": max(mem_mib) if mem_mib else None,
        "get_metrics_calls": len(metric_ms),
        "get_metrics_ms_mean": statistics.mean(metric_ms) if metric_ms else None,
        "get_metrics_ms_median": statistics.median(metric_ms) if metric_ms else None,
        "get_metrics_ms_p95": pct(metric_ms, 0.95),
        "get_metrics_ms_p99": pct(metric_ms, 0.99),
        "get_metrics_ms_max": max(metric_ms) if metric_ms else None,
        "sampled_items_mean": statistics.mean(sampled) if sampled else None,
        "sampled_items_max": max(sampled) if sampled else None,
        "queue_len_p95": pct(queue_len, 0.95),
        "queue_len_max": max(queue_len) if queue_len else None,
    }
    (run_dir / "scaler_overhead.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
