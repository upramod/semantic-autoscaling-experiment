#!/usr/bin/env bash
set -euo pipefail
CLUSTER=${CLUSTER:-semantic-scaling}
kind load docker-image --name "$CLUSTER" semantic-external-scaler:local semantic-worker:local semantic-loadgen:local
