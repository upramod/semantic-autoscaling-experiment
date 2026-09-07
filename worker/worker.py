import hashlib
import json
import math
import os
import socket
import time
import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
WORK_LIST = os.getenv("WORK_LIST", "work")
RESULT_LIST = os.getenv("RESULT_LIST", "results")
POD = os.getenv("HOSTNAME", socket.gethostname())

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def cpu_burn(seconds: float, seed: str):
    end = time.perf_counter() + max(0.0, seconds)
    value = seed.encode()
    while time.perf_counter() < end:
        value = hashlib.sha256(value).digest()
    return value


def execute(job: dict):
    # Real wall-clock work with a CPU component. This remains synthetic by design.
    service_s = max(0.05, float(job["service_s"]))
    kind = job.get("kind", "lookup")
    cpu_fraction = {"route": 0.20, "lookup": 0.30, "transform": 0.55, "doc": 0.70}.get(kind, 0.35)
    cpu_s = service_s * cpu_fraction
    sleep_s = service_s - cpu_s
    cpu_burn(cpu_s, str(job["id"]))
    if sleep_s > 0:
        time.sleep(sleep_s)


def main():
    print(json.dumps({"event": "worker_started", "pod": POD}), flush=True)
    while True:
        item = r.blpop(WORK_LIST, timeout=5)
        if not item:
            continue
        _, raw = item
        job = json.loads(raw)
        started = time.time()
        try:
            execute(job)
            status = "ok"
            error = None
        except Exception as exc:
            status = "error"
            error = repr(exc)
        finished = time.time()
        result = {
            "id": job["id"],
            "kind": job["kind"],
            "size_kb": job["size_kb"],
            "enqueued_at": job["enqueued_at"],
            "started_at": started,
            "finished_at": finished,
            "queue_delay_s": started - float(job["enqueued_at"]),
            "service_s": finished - started,
            "latency_s": finished - float(job["enqueued_at"]),
            "pod": POD,
            "status": status,
            "error": error,
        }
        r.rpush(RESULT_LIST, json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
