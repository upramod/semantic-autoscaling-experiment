#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker build -t semantic-external-scaler:local "$ROOT/scaler"
docker build -t semantic-worker:local "$ROOT/worker"
docker build -t semantic-loadgen:local "$ROOT/loadgen"
