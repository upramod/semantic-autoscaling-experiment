#!/usr/bin/env bash
set -euo pipefail
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ >/dev/null 2>&1 || true
helm repo update
cat >/tmp/metrics-server-values.yaml <<'EOF'
args:
  - --cert-dir=/tmp
  - --secure-port=10250
  - --kubelet-preferred-address-types=InternalIP,Hostname
  - --kubelet-use-node-status-port
  - --metric-resolution=15s
  - --kubelet-insecure-tls
EOF
helm upgrade --install metrics-server metrics-server/metrics-server \
  --namespace kube-system \
  -f /tmp/metrics-server-values.yaml \
  --wait --timeout 3m
kubectl rollout status deployment/metrics-server -n kube-system --timeout=180s
for i in $(seq 1 36); do
  if kubectl top nodes >/dev/null 2>&1; then
    kubectl top nodes
    exit 0
  fi
  sleep 5
done
echo "metrics API did not become ready" >&2
kubectl logs -n kube-system deployment/metrics-server --tail=200 || true
exit 1
