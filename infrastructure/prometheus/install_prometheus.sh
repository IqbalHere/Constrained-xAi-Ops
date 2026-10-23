#!/usr/bin/env bash
# ==============================================================================
# Prometheus Installation Script for Constrained-xAIOps Testbed
# Installs kube-prometheus-stack via Helm using values-minimal.yaml
# ==============================================================================

set -euo pipefail

NAMESPACE="monitoring"
RELEASE_NAME="prometheus-stack"
VALUES_FILE="$(dirname "$0")/values-minimal.yaml"

echo "=========================================================="
echo " Installing Prometheus Stack into namespace: ${NAMESPACE}"
echo "=========================================================="

if ! command -v helm >/dev/null 2>&1; then
    echo "[ERROR] Helm is required but not installed on PATH."
    exit 1
fi

echo "[INFO] Adding Prometheus Community Helm repository..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

echo "[INFO] Creating namespace ${NAMESPACE} if not present..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "[INFO] Deploying kube-prometheus-stack with ${VALUES_FILE}..."
helm upgrade --install "${RELEASE_NAME}" prometheus-community/kube-prometheus-stack \
    --namespace "${NAMESPACE}" \
    -f "${VALUES_FILE}" \
    --wait \
    --timeout 300s

echo "=========================================================="
echo " Prometheus Stack successfully installed!"
echo " Port-forward Prometheus server:"
echo "   kubectl port-forward -n ${NAMESPACE} svc/${RELEASE_NAME}-kube-prom-prometheus 9090:9090"
echo " Query endpoint: http://localhost:9090"
echo "=========================================================="
