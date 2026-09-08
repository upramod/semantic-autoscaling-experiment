#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEEDS=${SEEDS:-"1 2 3"}
DURATION=${DURATION:-180}
DRAIN_TIMEOUT=${DRAIN_TIMEOUT:-300}
export DURATION DRAIN_TIMEOUT

for policy in baseline semantic; do
  for scenario in steady composition volume mixed; do
    for seed in $SEEDS; do
      echo "=== ${policy} / ${scenario} / seed ${seed} ==="
      bash "$ROOT/scripts/run_experiment.sh" "$policy" "$scenario" "$seed"
    done
  done
done

python "$ROOT/analysis/aggregate.py" "$ROOT/results" | tee "$ROOT/results/aggregate.json"
