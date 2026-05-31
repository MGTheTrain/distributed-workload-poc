#!/bin/bash
#
# cleanup-kind.sh — tear down distributed-workload and clean up leftovers.
#
set -euo pipefail

NAMESPACE="${NAMESPACE:-ml-stack}"
RELEASE="${RELEASE:-distributed-workload}"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              Kind Cluster Cleanup                            ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# 1. Uninstall the umbrella — cascades to all subcharts.
echo -e "${YELLOW}⎈ Uninstalling ${RELEASE}...${NC}"
helm uninstall "${RELEASE}" -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true
echo -e "${GREEN}✓ Uninstalled${NC}"
echo ""

# 2. PVCs left by StatefulSets (Bitnami Postgres, Ray data) — Helm
#    leaves these by design so an upgrade doesn't lose data.
echo -e "${YELLOW}🗑  Removing PVCs left by StatefulSets...${NC}"
kubectl delete pvc -l app.kubernetes.io/instance="${RELEASE}" \
    -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true
echo -e "${GREEN}✓ PVCs cleared${NC}"
echo ""

# 3. The hostPath PV is cluster-scoped — namespace deletion won't touch it.
echo -e "${YELLOW}🗑  Removing cluster-scoped PV...${NC}"
kubectl delete pv ray-shared-data --ignore-not-found 2>/dev/null || true
echo -e "${GREEN}✓ PV cleared${NC}"
echo ""

# 4. Drop the namespace — sweeps anything Helm missed.
echo -e "${YELLOW}🧹 Deleting namespace...${NC}"
kubectl delete namespace "${NAMESPACE}" --ignore-not-found --timeout=60s
echo -e "${GREEN}✓ Namespace deleted${NC}"
echo ""

echo -e "${GREEN}✓ Cleanup complete — 'make k8s-deploy' to redeploy.${NC}"
