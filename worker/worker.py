import hashlib
import json
import os
import socket
import time

import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
WORK_LIST = os.getenv("WORK_LIST", "work")
RESULT_LIST = os.getenv("RESULT_LIST", "results")
POD = os.getenv("HOSTNAME", socket.gethostname())

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=10,
)


def wait_for_redis():
    attempt = 0

    while True:
        attempt += 1

        try:
            r.ping()

            print(
                json.dumps(
                    {
                        "event": "redis_connected",
                        "pod": POD,
                        "host": REDIS_HOST,
                        "port": REDIS_PORT,
                        "attempt": attempt,
                    }
                ),
                flush=True,
            )

            return

        except redis.RedisError as exc:
            print(
                json.dumps(
                    {
                        "event": "redis_connection_failed",
                        "pod": POD,
                        "attempt": attempt,
                        "error": repr(exc),
                    }
                ),
                flush=True,
            )

            time.sleep(min(5, attempt))


def cpu_burn(seconds: float, seed: str):
    end = time.perf_counter() + max(0.0, seconds)
    value = seed.encode()

    while time.perf_counter() < end:
        value = hashlib.sha256(value).digest()

    return value


def execute(job: dict):
    service_s = max(0.05, float(job["service_s"]))
    kind = job.get("kind", "lookup")

    cpu_fraction = {
        "route": 0.20,
        "lookup": 0.30,
        "transform": 0.55,
        "doc": 0.70,
    }.get(kind, 0.35)

    cpu_s = service_s * cpu_fraction
    sleep_s = service_s - cpu_s

    cpu_burn(cpu_s, str(job["id"]))

    if sleep_s > 0:
        time.sleep(sleep_s)


def process_message(raw: str):
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

    while True:
        try:
            r.rpush(
                RESULT_LIST,
                json.dumps(result, separators=(",", ":")),
            )
            return

        except redis.RedisError as exc:
            print(
                json.dumps(
                    {
                        "event": "result_write_retry",
                        "pod": POD,
                        "error": repr(exc),
                    }
                ),
                flush=True,
            )

            time.sleep(2)


def main():
    print(
        json.dumps(
            {
                "event": "worker_starting",
                "pod": POD,
                "redis_host": REDIS_HOST,
            }
        ),
        flush=True,
    )

    wait_for_redis()

    print(
        json.dumps(
            {
                "event": "worker_ready",
                "pod": POD,
            }
        ),
        flush=True,
    )

    while True:
        try:
            item = r.blpop(WORK_LIST, timeout=5)

            if not item:
                continue

            _, raw = item
            process_message(raw)

        except redis.RedisError as exc:
            print(
                json.dumps(
                    {
                        "event": "redis_runtime_error",
                        "pod": POD,
                        "error": repr(exc),
                    }
                ),
                flush=True,
            )

            time.sleep(2)

        except Exception as exc:
            # Keep the worker alive and expose unexpected failures
            # instead of letting Kubernetes enter CrashLoopBackOff.
            print(
                json.dumps(
                    {
                        "event": "worker_error",
                        "pod": POD,
                        "error": repr(exc),
                    }
                ),
                flush=True,
            )

            time.sleep(1)


if __name__ == "__main__":
    main()
