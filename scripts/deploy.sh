#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
kubectl apply -f "$ROOT/k8s/00-namespace.yaml"
kubectl apply -f "$ROOT/k8s/01-redis.yaml"
kubectl apply -f "$ROOT/k8s/02-worker.yaml"
kubectl apply -f "$ROOT/k8s/03-scaler.yaml"
kubectl rollout status deployment/redis -n semantic-scaling --timeout=120s
kubectl rollout status deployment/worker -n semantic-scaling --timeout=120s
kubectl rollout status deployment/semantic-external-scaler -n semantic-scaling --timeout=120s
