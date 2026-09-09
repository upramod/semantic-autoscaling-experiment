#!/usr/bin/env bash
set -euo pipefail
OUT=${1:?output csv required}
NAMESPACE=${NAMESPACE:-semantic-scaling}
INTERVAL=${INTERVAL:-15}
mkdir -p "$(dirname "$OUT")"
echo "timestamp,cpu,memory" > "$OUT"

while true; do
  TS=$(date +%s.%N)
  LINE=$(kubectl top pod -n "$NAMESPACE" -l app=semantic-external-scaler --containers --no-headers 2>/dev/null | head -n 1 || true)
  if [[ -n "$LINE" ]]; then
    CPU=$(awk '{print $(NF-1)}' <<<"$LINE")
    MEM=$(awk '{print $NF}' <<<"$LINE")
    echo "$TS,$CPU,$MEM" >> "$OUT"
  fi
  sleep "$INTERVAL"
done
