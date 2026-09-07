#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEEDS=${SEEDS:-"1 2 3"}
DURATION=${DURATION:-180}
export DURATION
for policy in baseline semantic; do
  for scenario in steady composition volume mixed; do
    for seed in $SEEDS; do
      "$ROOT/scripts/run_experiment.sh" "$policy" "$scenario" "$seed"
    done
  done
done
python "$ROOT/analysis/aggregate.py" "$ROOT/results"
