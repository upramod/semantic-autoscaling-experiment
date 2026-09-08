import csv
import json
import re
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
    ok_rows = [r for r in rows if r["status"] == "ok"]
    lat = [float(r["latency_s"]) for r in ok_rows]
    qd = [float(r["queue_delay_s"]) for r in ok_rows]
    service = [float(r["service_s"]) for r in ok_rows]

    rep = []
    with (d / "replicas.csv").open() as fh:
        for row in csv.DictReader(fh):
            rep.append((float(row["timestamp"]), int(row["desired"] or 0), int(row["available"] or 0)))

    replica_seconds = 0.0
    for a, b in zip(rep, rep[1:]):
        dt = max(0.0, b[0] - a[0])
        replica_seconds += a[2] * dt

    desired_changes = []
    for prev, cur in zip(rep, rep[1:]):
        delta = cur[1] - prev[1]
        if delta != 0:
            desired_changes.append((cur[0], delta))
    scale_up_events = sum(delta > 0 for _, delta in desired_changes)
    scale_down_events = sum(delta < 0 for _, delta in desired_changes)
    directions = [1 if delta > 0 else -1 for _, delta in desired_changes]
    oscillations = sum(a != b for a, b in zip(directions, directions[1:]))

    scenario_match = re.search(r"_(steady|composition|volume|mixed)_seed\d+$", d.name)
    scenario = scenario_match.group(1) if scenario_match else None
    first_scale_up_after_burst_s = None
    recovery_to_preburst_s = None
    observed_arrival_duration_s = None

    if ok_rows:
        enqueued = [float(r["enqueued_at"]) for r in ok_rows]
        arrival_start = min(enqueued)
        arrival_end = max(enqueued)
        observed_arrival_duration_s = max(0.0, arrival_end - arrival_start + 1.0)

        if scenario in {"composition", "volume", "mixed"} and rep:
            burst_start = arrival_start + observed_arrival_duration_s / 3.0
            burst_end = arrival_start + 2.0 * observed_arrival_duration_s / 3.0
            before = [sample for sample in rep if sample[0] <= burst_start]
            if before:
                pre_desired = before[-1][1]
                ups = [sample for sample in rep if sample[0] >= burst_start and sample[1] > pre_desired]
                if ups:
                    first_scale_up_after_burst_s = max(0.0, ups[0][0] - burst_start)
                recoveries = [sample for sample in rep if sample[0] >= burst_end and sample[1] <= pre_desired]
                if recoveries:
                    recovery_to_preburst_s = max(0.0, recoveries[0][0] - burst_end)

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
        "scaling_actions": len(desired_changes),
        "scale_up_events": scale_up_events,
        "scale_down_events": scale_down_events,
        "scaling_direction_reversals": oscillations,
        "first_scale_up_after_burst_s": first_scale_up_after_burst_s,
        "recovery_to_preburst_s": recovery_to_preburst_s,
        "observed_arrival_duration_s": observed_arrival_duration_s,
    }
    (d / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
