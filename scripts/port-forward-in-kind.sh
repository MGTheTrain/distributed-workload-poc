#!/bin/bash
set -e

# Color definitions
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'


# Trap to cleanup all background jobs on exit
cleanup() {
    echo ""
    echo -e "${YELLOW} Stopping all port-forwards...${NC}"
    jobs -p | xargs -r kill 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          Port-Forwarding Services from Kind Cluster          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if namespace exists
if [ "$FORWARD_ML" = true ] && ! kubectl get namespace ml-stack &> /dev/null; then
    echo -e "${YELLOW}  Namespace 'ml-stack' not found${NC}"
    echo -e "${YELLOW} Deploy first with: make k8s-deploy${NC}"
    exit 1
fi

echo -e "${GREEN} Starting port-forwards...${NC}"
echo ""

# Display and forward ML stack
echo -e "${BLUE}ML Stack:${NC}"
echo "  Ray Dashboard:  http://localhost:8265"
echo "  MLflow UI:      http://localhost:5000"
echo "  Prefect UI:     http://localhost:4200"
echo ""

kubectl port-forward -n ml-stack svc/ray-cluster-kuberay-head-svc 8265:8265 &
kubectl port-forward -n ml-stack svc/mlflow 5000:5000 &
kubectl port-forward -n ml-stack svc/prefect-server 4200:4200 &

echo -e "${GREEN}✓ Port-forwarding active!${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all port-forwards${NC}"
echo ""

# Wait for all background jobs
wait