#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLICY=${1:-baseline}       # baseline | cpu | weighted
SCENARIO=${2:-composition} # steady | composition | volume | mixed
SEED=${3:-1}
DURATION=${DURATION:-600}
DRAIN_TIMEOUT=${DRAIN_TIMEOUT:-900}
RESULT_ROOT=${RESULT_ROOT:-"$ROOT/results/validation"}
OUTDIR="$RESULT_ROOT/${POLICY}_${SCENARIO}_seed${SEED}"
mkdir -p "$OUTDIR"

capture_run_state() {
  kubectl exec -n semantic-scaling deployment/redis -- redis-cli --raw GET experiment:last_csv > "$OUTDIR/requests.csv" 2>/dev/null || true
  kubectl logs -n semantic-scaling deployment/semantic-external-scaler > "$OUTDIR/scaler.log" 2>&1 || true
  kubectl get hpa -n semantic-scaling -o yaml > "$OUTDIR/hpa.yaml" 2>&1 || true
  kubectl top pods -n semantic-scaling > "$OUTDIR/top-pods.txt" 2>&1 || true
}

kubectl delete scaledobject worker-scaling -n semantic-scaling --ignore-not-found
kubectl delete hpa worker-cpu-hpa -n semantic-scaling --ignore-not-found
kubectl wait --for=delete hpa/keda-hpa-worker-scaling -n semantic-scaling --timeout=60s >/dev/null 2>&1 || true
kubectl scale deployment worker -n semantic-scaling --replicas=2
kubectl rollout status deployment/worker -n semantic-scaling --timeout=120s
kubectl exec -n semantic-scaling deployment/redis -- redis-cli DEL work results experiment:last_csv experiment:last_meta >/dev/null

case "$POLICY" in
  baseline)
    kubectl apply -f "$ROOT/k8s/08-scaledobject-baseline-validation.yaml"
    kubectl wait --for=condition=Ready scaledobject/worker-scaling -n semantic-scaling --timeout=120s
    ;;
  weighted)
    kubectl apply -f "$ROOT/k8s/09-scaledobject-weighted-validation.yaml"
    kubectl wait --for=condition=Ready scaledobject/worker-scaling -n semantic-scaling --timeout=120s
    ;;
  cpu)
    kubectl apply -f "$ROOT/k8s/10-hpa-cpu-validation.yaml"
    ;;
  *)
    echo "unknown policy: $POLICY" >&2
    exit 2
    ;;
esac

# Give each controller the same quiet interval before arrivals begin.
sleep 20

bash "$ROOT/scripts/monitor_replicas.sh" "$OUTDIR/replicas.csv" &
MON_PID=$!
trap 'kill "$MON_PID" 2>/dev/null || true' EXIT

kubectl delete job loadgen -n semantic-scaling --ignore-not-found
sed \
  -e "s/--scenario=composition/--scenario=${SCENARIO}/" \
  -e "s/--duration=180/--duration=${DURATION}/" \
  -e "s/--seed=1/--seed=${SEED}/" \
  -e "s/--drain-timeout=900/--drain-timeout=${DRAIN_TIMEOUT}/" \
  "$ROOT/k8s/06-loadgen-job.yaml" | kubectl apply -f -

DEADLINE=$((SECONDS + DURATION + DRAIN_TIMEOUT + 180))
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
    capture_run_state
    echo "loadgen job failed" >&2
    exit 1
  fi

  if (( SECONDS >= DEADLINE )); then
    POD=$(kubectl get pod -n semantic-scaling -l job-name=loadgen -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -n "$POD" ]]; then
      kubectl logs -n semantic-scaling "$POD" | tee "$OUTDIR/loadgen.log" >&2 || true
    fi
    capture_run_state
    echo "timed out waiting for loadgen" >&2
    exit 1
  fi

  sleep 5
done

kill "$MON_PID" 2>/dev/null || true
trap - EXIT

POD=$(kubectl get pod -n semantic-scaling -l job-name=loadgen -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n semantic-scaling deployment/redis -- redis-cli --raw GET experiment:last_csv > "$OUTDIR/requests.csv"
kubectl logs -n semantic-scaling "$POD" > "$OUTDIR/loadgen.log"
kubectl logs -n semantic-scaling deployment/semantic-external-scaler > "$OUTDIR/scaler.log" 2>&1 || true
kubectl get hpa -n semantic-scaling -o yaml > "$OUTDIR/hpa.yaml" 2>&1 || true
kubectl top pods -n semantic-scaling > "$OUTDIR/top-pods.txt" 2>&1 || true
python "$ROOT/analysis/analyze_run.py" "$OUTDIR"

echo "Results: $OUTDIR"
