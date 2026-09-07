#!/usr/bin/env bash
set -euo pipefail
missing=0
for cmd in docker kubectl helm kind python; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "OK   $cmd: $(command -v "$cmd")"
  else
    echo "MISS $cmd"
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  echo "Install the missing prerequisites before running the Kubernetes experiment." >&2
  exit 1
fi
echo "Preflight passed."
