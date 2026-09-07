#!/usr/bin/env bash
set -euo pipefail
OUT=${1:-replicas.csv}
echo "timestamp,desired,available" > "$OUT"
while true; do
  ts=$(date +%s.%N)
  desired=$(kubectl get deployment worker -n semantic-scaling -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 0)
  available=$(kubectl get deployment worker -n semantic-scaling -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo 0)
  available=${available:-0}
  echo "$ts,$desired,$available" >> "$OUT"
  sleep 2
done
