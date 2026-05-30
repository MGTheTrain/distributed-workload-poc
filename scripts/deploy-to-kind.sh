#!/bin/bash
#
# deploy-to-kind.sh — install distributed-workload-platform into kind.
#
# Pipeline:
#   1. Add Helm repos (idempotent)
#   2. Resolve chart dependencies
#   3. helm upgrade --install
#
set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

CHART="./infra/helm-charts/distributed-workload-platform"
NAMESPACE="${NAMESPACE:-ml-stack}"
RELEASE="${RELEASE:-distributed-workload}"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Deploy distributed-workload-platform on Kind                ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─── 1. Helm repos ──────────────────────────────────────────────────────────
echo -e "${YELLOW}📚 Adding Helm repositories...${NC}"
helm repo add localstack https://localstack.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add kuberay    https://ray-project.github.io/kuberay-helm/ >/dev/null 2>&1 || true
helm repo update >/dev/null
echo -e "${GREEN}✓ Repositories ready${NC}"
echo ""

# ─── 2. Dependencies ────────────────────────────────────────────────────────
echo -e "${YELLOW}⎈ Resolving chart dependencies...${NC}"
helm dependency update "${CHART}" >/dev/null
echo -e "${GREEN}✓ Dependencies resolved${NC}"
echo ""

# ─── 3. Install ─────────────────────────────────────────────────────────────
echo -e "${YELLOW}⎈ Installing ${RELEASE}...${NC}"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install "${RELEASE}" "${CHART}" \
    --namespace "${NAMESPACE}" \
    --wait --timeout 5m
echo -e "${GREEN}✓ ${RELEASE} deployed${NC}"
echo ""

helm list -n "${NAMESPACE}" || true