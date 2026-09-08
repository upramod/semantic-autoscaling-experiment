#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLICY=${1:-baseline}       # baseline | semantic
SCENARIO=${2:-composition} # steady | composition | volume | mixed
SEED=${3:-1}
DURATION=${DURATION:-180}
OUTDIR="$ROOT/results/${POLICY}_${SCENARIO}_seed${SEED}"
mkdir -p "$OUTDIR"

kubectl delete scaledobject worker-scaling -n semantic-scaling --ignore-not-found
kubectl wait --for=delete hpa/keda-hpa-worker-scaling -n semantic-scaling --timeout=60s >/dev/null 2>&1 || true
kubectl scale deployment worker -n semantic-scaling --replicas=2
kubectl exec -n semantic-scaling deployment/redis -- redis-cli DEL work results experiment:last_csv experiment:last_meta >/dev/null

if [[ "$POLICY" == "semantic" ]]; then
  kubectl apply -f "$ROOT/k8s/05-scaledobject-semantic.yaml"
else
  kubectl apply -f "$ROOT/k8s/04-scaledobject-baseline.yaml"
fi

kubectl wait --for=condition=Ready scaledobject/worker-scaling -n semantic-scaling --timeout=120s

bash "$ROOT/scripts/monitor_replicas.sh" "$OUTDIR/replicas.csv" &
MON_PID=$!
trap 'kill "$MON_PID" 2>/dev/null || true' EXIT

kubectl delete job loadgen -n semantic-scaling --ignore-not-found
sed \
  -e "s/--scenario=composition/--scenario=${SCENARIO}/" \
  -e "s/--duration=180/--duration=${DURATION}/" \
  -e "s/--seed=1/--seed=${SEED}/" \
  "$ROOT/k8s/06-loadgen-job.yaml" | kubectl apply -f -

# Wait for the Job to complete, but fail fast if the pod terminates with an error.
DEADLINE=$((SECONDS + 1200))
while true; do
  COMPLETE=$(kubectl get job loadgen -n semantic-scaling -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || true)
  FAILED=$(kubectl get job loadgen -n semantic-scaling -o jsonpath='{.status.failed}' 2>/dev/null || true)

  if [[ "$COMPLETE" == "True" ]]; then
    break
  fi

  if [[ -n "$FAILED" && "$FAILED" != "0" ]]; then
    POD=$(kubectl get pod -n semantic-scaling -l job-name=loadgen -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -n "$POD" ]]; then
      kubectl logs -n semantic-scaling "$POD" | tee "$OUTDIR/loadgen.log" >&2 || true
    fi
    echo "loadgen job failed" >&2
    exit 1
  fi

  if (( SECONDS >= DEADLINE )); then
    POD=$(kubectl get pod -n semantic-scaling -l job-name=loadgen -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -n "$POD" ]]; then
      kubectl logs -n semantic-scaling "$POD" | tee "$OUTDIR/loadgen.log" >&2 || true
    fi
    echo "timed out waiting for loadgen" >&2
    exit 1
  fi

  sleep 5
done

kill "$MON_PID" 2>/dev/null || true
trap - EXIT

POD=$(kubectl get pod -n semantic-scaling -l job-name=loadgen -o jsonpath='{.items[0].metadata.name}')
# The completed Job stores its CSV in Redis because kubectl cp requires a running container.
kubectl exec -n semantic-scaling deployment/redis -- redis-cli --raw GET experiment:last_csv > "$OUTDIR/requests.csv"
kubectl logs -n semantic-scaling "$POD" > "$OUTDIR/loadgen.log"
kubectl logs -n semantic-scaling deployment/semantic-external-scaler > "$OUTDIR/scaler.log" || true
kubectl get hpa -n semantic-scaling -o yaml > "$OUTDIR/hpa.yaml" || true
python "$ROOT/analysis/analyze_run.py" "$OUTDIR"

echo "Results: $OUTDIR"
