#!/usr/bin/env bash
set -euo pipefail
CLUSTER=${CLUSTER:-semantic-scaling}
if ! command -v kind >/dev/null; then
  echo "kind is required: https://kind.sigs.k8s.io/" >&2
  exit 1
fi
kind create cluster --name "$CLUSTER" --wait 120s
