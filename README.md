# Semantic Cost-Aware Autoscaling Prototype

A reproducible KEDA reference implementation for testing whether a bounded estimate of queued work cost improves autoscaling for heterogeneous event-driven workloads.

## What this prototype measures

Two policies scale the same Redis-backed worker deployment:

1. **Baseline:** KEDA's native Redis List scaler uses queue length with a target of six queued messages per replica.
2. **Semantic hybrid:** the same queue-length trigger remains as a safety floor, while a KEDA external gRPC scaler samples queued message metadata, estimates total outstanding work in service-seconds, and exposes that as a second external metric. Kubernetes HPA can therefore react to whichever trigger asks for more replicas.

The default semantic estimator is deterministic and local so the experiment is reproducible without external services. An optional chat-completions-compatible estimator is included for a later LLM experiment. The LLM estimator is intentionally not required for the primary testbed.

## Queue and workload model

Redis List `work` stores synthetic JSON jobs. Producers use `RPUSH`; workers consume with `BLPOP`. The external scaler reads a bounded prefix with `LRANGE`, which does not remove queued items.

Each job contains:

```json
{
  "id": "uuid",
  "kind": "route|lookup|transform|doc",
  "size_kb": 41.2,
  "priority": "normal|high",
  "service_s": 3.7,
  "enqueued_at": 1788810000.0
}
```

The worker executes actual wall-clock synthetic work with a CPU-bound SHA-256 component plus sleep. Results are written to a separate Redis List and include queue delay, service time, end-to-end latency, and worker pod.

## Repository layout

- `scaler/`: KEDA external scaler, KEDA v2.20 protobuf contract, metadata estimator, optional LLM estimator.
- `worker/`: single-message-at-a-time worker.
- `loadgen/`: four reproducible workload profiles.
- `k8s/`: Redis, worker, external scaler, baseline ScaledObject, semantic ScaledObject, load generator Job.
- `scripts/`: build, kind, KEDA install, deployment, monitoring, and experiment automation.
- `analysis/`: per-run and aggregate metrics.

## Prerequisites

- Docker
- `kubectl`
- Helm 3
- kind
- Python 3 for local result analysis

The scripts install KEDA 2.20.0. If you already have a compatible KEDA installation, skip that step.

## Run the testbed

```bash
./scripts/build_images.sh
./scripts/kind_create.sh
./scripts/kind_load_images.sh
./scripts/install_keda.sh
./scripts/deploy.sh
```

Check the platform:

```bash
kubectl get pods -n semantic-scaling
kubectl get scaledobjects -n semantic-scaling
```

Run one baseline composition-shift experiment:

```bash
./scripts/run_experiment.sh baseline composition 1
```

Run the corresponding semantic-cost experiment:

```bash
./scripts/run_experiment.sh semantic composition 1
```

Run the default matrix of three seeds for four scenarios and two policies:

```bash
SEEDS="1 2 3" DURATION=180 ./scripts/run_matrix.sh
```

Outputs are stored under `results/`. Each run contains:

- `requests.csv`: measured queue delay, service time, and end-to-end latency.
- `replicas.csv`: desired and available replica counts sampled every two seconds.
- `summary.json`: P95/P99 latency, 20-second SLO violation rate, replica-seconds, and peak replica counts.
- `scaler.log`: work estimates emitted by the external scaler.
- `hpa.yaml`: final HPA state.

`results/aggregate.csv` summarizes repeated runs.

## Workload scenarios

- `steady`: normal mixture and arrival rate.
- `composition`: constant arrival rate, but the middle third becomes semantically heavier.
- `volume`: higher arrival rate in the middle third, normal mixture.
- `mixed`: both volume and workload complexity increase.

The composition scenario is the central test. Queue length alone observes roughly the same count even though mean service cost rises.

## External scaler contract

The scaler implements KEDA's pull-based gRPC methods:

- `IsActive`
- `GetMetricSpec`
- `GetMetrics`

`GetMetrics` estimates:

```
estimated_total_work = current_queue_length * mean(sampled_cost_seconds)
```

`GetMetricSpec` sets `targetWork` to the amount of queued service work one replica should absorb. The semantic ScaledObject keeps the native Redis List trigger, so a semantic underestimate cannot suppress the ordinary queue-length scaling signal.

## Optional LLM estimator

Change `estimator: metadata` to `estimator: llm` in `k8s/05-scaledobject-semantic.yaml` and configure the scaler deployment with:

```text
LLM_ENDPOINT=<full chat-completions-compatible HTTP endpoint>
LLM_API_KEY=<key>
LLM_MODEL=<optional model/deployment>
LLM_AUTH_HEADER=Authorization
LLM_AUTH_PREFIX=Bearer 
```

For providers that use an `api-key` header, set `LLM_AUTH_HEADER=api-key` and `LLM_AUTH_PREFIX=`.

The LLM path has a short timeout, a sample cache, and deterministic metadata fallback. The native queue-length trigger remains enabled. Do not expose sensitive production payloads to an external model solely for scaling.

## Experimental discipline

This repository is a synthetic benchmark. It does not reproduce or claim measurements from any prior enterprise POC. Any paper results should be generated from actual runs of this repository, with cluster size, Kubernetes version, KEDA version, node type, estimator mode, poll interval, and seed count reported.

Recommended paper runs: at least 10 seeds per policy/scenario after tuning the workload to the chosen cluster capacity. Run baseline and semantic trials on the same cluster and avoid other resource-intensive workloads while collecting measurements.

## Run entirely in GitHub Actions

If you do not want to install Docker or Kubernetes locally, use the included
`.github/workflows/experiment.yml` workflow.

Upload this repository to GitHub, open **Actions -> KEDA Semantic Autoscaling Experiment**,
and run `smoke` first. The workflow creates a temporary kind cluster on a GitHub-hosted
runner, installs KEDA, builds the worker/scaler/load-generator images, executes the
baseline and semantic experiments, and uploads the measurements as an Actions artifact.

After the smoke run succeeds, choose `paper` to execute the 24-run experimental matrix.

