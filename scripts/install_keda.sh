#!/usr/bin/env bash
set -euo pipefail
helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1 || true
helm repo update
helm upgrade --install keda kedacore/keda --namespace keda --create-namespace --version 2.20.0
kubectl rollout status deployment/keda-operator -n keda --timeout=180s
