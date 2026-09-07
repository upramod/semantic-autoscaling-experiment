import csv
import json
import sys
from pathlib import Path
from statistics import mean


def percentile(values, p):
    xs = sorted(values)
    if not xs:
        return float("nan")
    idx = (len(xs) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(xs) - 1)
    frac = idx - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def main():
    d = Path(sys.argv[1])
    with (d / "requests.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    lat = [float(r["latency_s"]) for r in rows if r["status"] == "ok"]
    qd = [float(r["queue_delay_s"]) for r in rows if r["status"] == "ok"]
    service = [float(r["service_s"]) for r in rows if r["status"] == "ok"]

    rep = []
    with (d / "replicas.csv").open() as fh:
        for row in csv.DictReader(fh):
            rep.append((float(row["timestamp"]), int(row["desired"] or 0), int(row["available"] or 0)))
    replica_seconds = 0.0
    for a, b in zip(rep, rep[1:]):
        dt = max(0.0, b[0] - a[0])
        replica_seconds += a[2] * dt

    summary = {
        "completed": len(lat),
        "mean_latency_s": mean(lat) if lat else None,
        "p95_latency_s": percentile(lat, 0.95),
        "p99_latency_s": percentile(lat, 0.99),
        "slo_20s_violation_rate": sum(v > 20 for v in lat) / len(lat) if lat else None,
        "mean_queue_delay_s": mean(qd) if qd else None,
        "mean_service_s": mean(service) if service else None,
        "replica_seconds": replica_seconds,
        "replica_seconds_per_request": replica_seconds / len(lat) if lat else None,
        "max_desired_replicas": max((x[1] for x in rep), default=0),
        "max_available_replicas": max((x[2] for x in rep), default=0),
    }
    (d / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
