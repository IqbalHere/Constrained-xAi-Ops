#!/usr/bin/env bash
# ==============================================================================
# Minikube & Cluster Setup Script for Constrained-xAIOps Operational Testbed
# Target Systems: Google Cloud Online Boutique on Minikube / Kind
# ==============================================================================

set -euo pipefail

PROFILE="${1:-standard}"
echo "=========================================================="
echo " Starting Constrained-xAIOps Testbed Setup (Profile: ${PROFILE})"
echo "=========================================================="

# Resource profiles
if [ "${PROFILE}" = "lightweight" ]; then
    CPUS=2
    MEMORY=3584
    echo "[INFO] Using Lightweight Resource Profile: ${CPUS} CPUs, ${MEMORY} MB RAM"
else
    CPUS=4
    MEMORY=8192
    echo "[INFO] Using Standard Resource Profile: ${CPUS} CPUs, ${MEMORY} MB RAM"
fi

# 1. Check or start Minikube
if command -v minikube >/dev/null 2>&1; then
    echo "[INFO] Minikube detected. Launching cluster..."
    minikube start \
        --cpus="${CPUS}" \
        --memory="${MEMORY}" \
        --driver=docker \
        --kubernetes-version=v1.28.3 \
        --addons=metrics-server,ingress
    echo "[INFO] Minikube cluster active."
elif command -v kind >/dev/null 2>&1; then
    echo "[INFO] Kind detected. Creating Kind cluster from kind_config.yaml..."
    kind create cluster --config="$(dirname "$0")/kind_config.yaml" || true
else
    echo "[ERROR] Neither minikube nor kind was found on PATH."
    echo "[ERROR] Please install minikube or kind to proceed with local cluster testing."
    exit 1
fi

# 2. Verify kubectl connectivity
echo "[INFO] Verifying cluster nodes..."
kubectl get nodes -o wide

# 3. Create testbed namespaces
echo "[INFO] Creating namespaces: boutique and monitoring..."
kubectl create namespace boutique --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# 4. Deploy Online Boutique
MANIFEST_PATH="$(dirname "$0")/../online-boutique/kubernetes-manifests.yaml"
if [ -f "${MANIFEST_PATH}" ]; then
    echo "[INFO] Deploying Online Boutique from ${MANIFEST_PATH}..."
    kubectl apply -n boutique -f "${MANIFEST_PATH}"
    echo "[INFO] Waiting for core microservices to reach Ready state (timeout 180s)..."
    kubectl rollout status deployment/frontend -n boutique --timeout=180s || true
else
    echo "[WARN] Manifest not found at ${MANIFEST_PATH}."
fi

echo "=========================================================="
echo " Constrained-xAIOps Cluster Ready!"
echo " Frontend port-forward command:"
echo "   kubectl port-forward -n boutique svc/frontend 8080:80"
echo "=========================================================="
