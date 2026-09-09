import argparse
import csv
import io
import json
import math
import random
import time
import uuid
from pathlib import Path
import redis

BASE_SECONDS = {"route": 0.35, "lookup": 0.90, "transform": 2.80, "doc": 7.50}
SLOPES = {"route": 0.0008, "lookup": 0.0010, "transform": 0.0015, "doc": 0.0020}
BASE_MIX = {"route": 0.72, "lookup": 0.18, "transform": 0.08, "doc": 0.02}
HEAVY_MIX = {"route": 0.30, "lookup": 0.20, "transform": 0.25, "doc": 0.25}
SIZE_MEDIAN = {"route": 12, "lookup": 18, "transform": 25, "doc": 35}


def choose(rng, mix):
    x = rng.random()
    acc = 0.0
    for k, p in mix.items():
        acc += p
        if x <= acc:
            return k
    return next(reversed(mix))


def profile(scenario, elapsed, duration, base_rate=4.0, burst_rate=7.0):
    burst_start = duration / 3
    burst_end = 2 * duration / 3
    in_burst = burst_start <= elapsed < burst_end
    if scenario == "steady":
        return base_rate, BASE_MIX
    if scenario == "composition":
        return base_rate, HEAVY_MIX if in_burst else BASE_MIX
    if scenario == "volume":
        return (burst_rate if in_burst else base_rate), BASE_MIX
    if scenario == "mixed":
        return (burst_rate if in_burst else base_rate), (HEAVY_MIX if in_burst else BASE_MIX)
    raise ValueError(scenario)


def sample_job(rng, scenario, elapsed, duration, base_rate=4.0, burst_rate=7.0):
    rate, mix = profile(scenario, elapsed, duration, base_rate, burst_rate)
    kind = choose(rng, mix)
    median = SIZE_MEDIAN[kind]
    size_kb = rng.lognormvariate(math.log(median), 0.65)
    mean_service = BASE_SECONDS[kind] + SLOPES[kind] * size_kb
    # Stable, bounded service variation to avoid pathological long tails.
    service_s = max(0.10, min(20.0, mean_service * rng.lognormvariate(-0.02, 0.20)))
    return rate, kind, size_kb, service_s


def poisson_knuth(rng, lam):
    # Fine for the small per-second lambda used in this prototype.
    limit = math.exp(-lam)
    k = 0
    p = 1.0
    while p > limit:
        k += 1
        p *= rng.random()
    return k - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--redis-host", default="redis")
    ap.add_argument("--redis-port", type=int, default=6379)
    ap.add_argument("--scenario", choices=["steady", "composition", "volume", "mixed"], default="composition")
    ap.add_argument("--duration", type=int, default=180)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--base-rate", type=float, default=4.0)
    ap.add_argument("--burst-rate", type=float, default=7.0)
    ap.add_argument("--output", default="/results/run.csv")
    ap.add_argument("--drain-timeout", type=int, default=900)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    client = redis.Redis(host=args.redis_host, port=args.redis_port, decode_responses=True)
    work = "work"
    results = "results"
    client.delete(work, results)

    sent = 0
    start = time.time()
    next_tick = start
    while True:
        now = time.time()
        elapsed = now - start
        if elapsed >= args.duration:
            break
        if now < next_tick:
            time.sleep(min(0.05, next_tick - now))
            continue
        rate, _, _, _ = sample_job(
            rng, args.scenario, elapsed, args.duration, args.base_rate, args.burst_rate
        )
        count = poisson_knuth(rng, rate)
        for _ in range(count):
            _, kind, size_kb, service_s = sample_job(
                rng, args.scenario, elapsed, args.duration, args.base_rate, args.burst_rate
            )
            job = {
                "id": str(uuid.uuid4()),
                "kind": kind,
                "size_kb": round(size_kb, 3),
                "priority": "high" if rng.random() < 0.08 else "normal",
                "service_s": round(service_s, 4),
                "enqueued_at": time.time(),
            }
            client.rpush(work, json.dumps(job, separators=(",", ":")))
            sent += 1
        next_tick += 1.0

    rows = []
    deadline = time.time() + args.drain_timeout
    while len(rows) < sent and time.time() < deadline:
        item = client.blpop(results, timeout=2)
        if item:
            rows.append(json.loads(item[1]))

    fields = ["id", "kind", "size_kb", "enqueued_at", "started_at", "finished_at", "queue_delay_s", "service_s", "latency_s", "pod", "status", "error"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    csv_text = buf.getvalue()
    # Persist through Redis so results remain available after this Kubernetes Job exits.
    client.set("experiment:last_csv", csv_text, ex=86400)
    client.set(
        "experiment:last_meta",
        json.dumps({
            "scenario": args.scenario,
            "seed": args.seed,
            "sent": sent,
            "base_rate": args.base_rate,
            "burst_rate": args.burst_rate,
        }),
        ex=86400,
    )

    # Also write locally when the load generator is run outside Kubernetes.
    out = Path(args.output)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(csv_text)
    except OSError:
        pass

    summary = {
        "scenario": args.scenario,
        "seed": args.seed,
        "sent": sent,
        "completed": len(rows),
        "base_rate": args.base_rate,
        "burst_rate": args.burst_rate,
        "output": str(out),
        "queue_remaining": client.llen(work),
    }
    print(json.dumps(summary), flush=True)
    if len(rows) != sent:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
