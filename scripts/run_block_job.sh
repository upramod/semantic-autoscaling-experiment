#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCENARIO=${1:?scenario required}
SEED=${2:?seed required}
RESULT_ROOT=${RESULT_ROOT:-"$ROOT/results/blocked"}
DURATION=${DURATION:-600}
DRAIN_TIMEOUT=${DRAIN_TIMEOUT:-900}
BASE_RATE=${BASE_RATE:-2.5}
BURST_RATE=${BURST_RATE:-4.0}
export RESULT_ROOT DURATION DRAIN_TIMEOUT BASE_RATE BURST_RATE

META_DIR="$RESULT_ROOT/metadata/${SCENARIO}_seed${SEED}"
mkdir -p "$META_DIR"

# Ten counterbalanced orders: five cyclic rotations followed by their reversals.
# Within each scenario, every policy occupies every ordinal position twice across seeds 1-10.
ORDER=$(python - "$SEED" <<'PY'
import sys
seed = int(sys.argv[1])
base = ["baseline", "weighted", "cpu50", "cpu70", "cpu90"]
orders = []
for i in range(5):
    orders.append(base[i:] + base[:i])
for i in range(5):
    orders.append(list(reversed(orders[i])))
print(" ".join(orders[(seed - 1) % 10]))
PY
)
printf '%s\n' "$ORDER" > "$META_DIR/policy-order.txt"

{
  echo "scenario=${SCENARIO}"
  echo "seed=${SEED}"
  echo "policy_order=${ORDER}"
  echo "duration=${DURATION}"
  echo "base_rate=${BASE_RATE}"
  echo "burst_rate=${BURST_RATE}"
  echo "date_utc=$(date -u --iso-8601=seconds)"
  echo
  uname -a
  echo
  nproc
  echo
  free -h
  echo
  lscpu
} > "$META_DIR/host.txt" 2>&1

capture_diagnostics() {
  local policy=$1
  local dir="$RESULT_ROOT/diagnostics/${SCENARIO}_seed${SEED}/${policy}"
  mkdir -p "$dir"
  kubectl get all -A -o wide > "$dir/all-resources.txt" 2>&1 || true
  kubectl get scaledobjects,hpa -A -o yaml > "$dir/scaling.yaml" 2>&1 || true
  kubectl top nodes > "$dir/top-nodes.txt" 2>&1 || true
  kubectl top pods -A > "$dir/top-pods.txt" 2>&1 || true
  kubectl describe pods -n semantic-scaling > "$dir/pods-describe.txt" 2>&1 || true
  kubectl logs -n semantic-scaling deployment/semantic-external-scaler --tail=-1 > "$dir/scaler.log" 2>&1 || true
  kubectl logs -n keda deployment/keda-operator --tail=2000 > "$dir/keda-operator.log" 2>&1 || true
  kubectl logs -n kube-system deployment/metrics-server --tail=1000 > "$dir/metrics-server.log" 2>&1 || true
}

for POLICY in $ORDER; do
  echo "=== blocked validation ${SCENARIO} seed ${SEED}: ${POLICY} ==="

  # Recreate Kubernetes for every treatment while preserving the same physical runner.
  kind delete cluster --name semantic-scaling >/dev/null 2>&1 || true
  bash "$ROOT/scripts/kind_create.sh"
  bash "$ROOT/scripts/kind_load_images.sh"
  bash "$ROOT/scripts/install_keda.sh"
  bash "$ROOT/scripts/install_metrics_server.sh"
  bash "$ROOT/scripts/deploy.sh"

  {
    echo "policy=${POLICY}"
    echo "scenario=${SCENARIO}"
    echo "seed=${SEED}"
    echo "date_utc=$(date -u --iso-8601=seconds)"
    echo
    kubectl get nodes -o wide
    echo
    kubectl top nodes
    echo
    kubectl version
    echo
    helm version
    echo
    kind version
  } > "$META_DIR/cluster-${POLICY}.txt" 2>&1

  if ! bash "$ROOT/scripts/run_block_policy.sh" "$POLICY" "$SCENARIO" "$SEED"; then
    capture_diagnostics "$POLICY"
    exit 1
  fi
  capture_diagnostics "$POLICY"
done

kind delete cluster --name semantic-scaling >/dev/null 2>&1 || true
