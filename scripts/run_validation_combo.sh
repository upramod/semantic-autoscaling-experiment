#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLICY=${1:?policy required}
SCENARIO=${2:?scenario required}
SEEDS=${SEEDS:-"1 2 3 4 5"}
DURATION=${DURATION:-600}
DRAIN_TIMEOUT=${DRAIN_TIMEOUT:-900}
export DURATION DRAIN_TIMEOUT

for seed in $SEEDS; do
  echo "=== validation ${POLICY} / ${SCENARIO} / seed ${seed} ==="
  bash "$ROOT/scripts/run_validation_experiment.sh" "$POLICY" "$SCENARIO" "$seed"
done
