#!/bin/bash
set -e

# Color definitions
BLUE='\033[0;34m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                 Setup Script                                 ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# System requirements check
echo -e "${CYAN}📋 System Requirements:${NC}"
echo -e "${YELLOW} • Disk Space: 20-30+ GB available${NC}"
echo -e "${YELLOW} • Memory: 16+ GB${NC}"
echo -e "${YELLOW} • Docker: daemon running with sufficient resources${NC}"
echo ""

# Architecture detection
if [ $(uname -m) = x86_64 ]; then
    ARCH="amd64"
elif [ $(uname -m) = aarch64 ]; then
    ARCH="arm64"
else
    echo -e "${RED}Unsupported architecture: $(uname -m)${NC}"
    exit 1
fi
echo -e "${BLUE}Detected architecture: $ARCH${NC}"

# Docker daemon check
echo -e "${BLUE}Waiting for Docker daemon to be ready...${NC}"
timeout 30 bash -c 'until docker info > /dev/null 2>&1; do sleep 1; done' || {
    echo -e "${RED}Docker daemon failed to start within 30 seconds${NC}"
    exit 1
}
echo -e "${GREEN}Docker daemon is ready${NC}"

# Install Kind
KIND_RELEASE="v0.29.0"
echo -e "${BLUE}Installing Kind...${NC}"
curl -Lo ./kind https://kind.sigs.k8s.io/dl/$KIND_RELEASE/kind-linux-${ARCH}
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# Create cluster
kind delete cluster --name kind || true
echo -e "${BLUE}Creating kind cluster with fixed ports...${NC}"
kind create cluster --name kind --wait=180s

# Store kubeconfig
kind get kubeconfig --name kind --internal=false > ~/.kube/config

# Test cluster
if kubectl get nodes > /dev/null 2>&1; then
    echo -e "${GREEN}Kind cluster ready${NC}"
    kubectl cluster-info
    kubectl get nodes
    kubectl get pods --all-namespaces
else
    echo -e "${RED}Cluster failed to start properly${NC}"
    docker logs kind-control-plane
    exit 1
fi

# Install pip depenencies
echo -e "${BLUE}Installing pip dependencies...${NC}"

pip install --break-system-packages \
    pillow==12.0.0 \
    colorama==0.4.6 \
    pandas==2.3.3 \
    pyarrow==19.0.1 \
    fastparquet==2024.11.0 \
    numpy==1.26.4 \
    torch==2.9.1 \
    torchvision==0.24.1 \
    pydantic==2.11.7 \
    boto3==1.42.10 \
    mlflow==3.7.0 \
    hyperopt==0.2.7 \
    prefect==3.6.6 \
    ray==2.51.1

echo -e "${GREEN}Setup complete.${NC}"