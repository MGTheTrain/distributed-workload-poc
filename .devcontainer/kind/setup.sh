#!/bin/bash
#
# Setup script for the Kind cluster environment.
#
# Each step is a function so failures point at a named step and you
# can re-run a single phase by sourcing this file and calling its
# function directly (e.g. `source setup.sh && install_kind`).
#
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────
BLUE='\033[0;34m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

KIND_RELEASE="v0.29.0"
CLUSTER_NAME="kind"

# ── Helpers ──────────────────────────────────────────────────────────
banner() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ $1${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

log()  { echo -e "${BLUE}$*${NC}"; }
ok()   { echo -e "${GREEN}$*${NC}"; }
warn() { echo -e "${YELLOW}$*${NC}"; }
err()  { echo -e "${RED}$*${NC}" >&2; }

# ── Steps ────────────────────────────────────────────────────────────
print_requirements() {
    echo -e "${CYAN}📋 System Requirements:${NC}"
    warn " • Disk Space: 20-30+ GB available"
    warn " • Memory: 16+ GB"
    warn " • Docker: daemon running with sufficient resources"
    echo ""
}

detect_arch() {
    case "$(uname -m)" in
        x86_64)  ARCH="amd64" ;;
        aarch64) ARCH="arm64" ;;
        *) err "Unsupported architecture: $(uname -m)"; exit 1 ;;
    esac
    log "Detected architecture: ${ARCH}"
}

wait_for_docker() {
    log "Waiting for Docker daemon to be ready..."
    if ! timeout 30 bash -c 'until docker info >/dev/null 2>&1; do sleep 1; done'; then
        err "Docker daemon failed to start within 30 seconds"
        exit 1
    fi
    ok "Docker daemon is ready"
}

install_kind() {
    if command -v kind >/dev/null 2>&1; then
        log "kind already installed: $(kind --version)"
        return
    fi
    log "Installing kind ${KIND_RELEASE}..."
    curl -fsSLo /tmp/kind \
        "https://kind.sigs.k8s.io/dl/${KIND_RELEASE}/kind-linux-${ARCH}"
    chmod +x /tmp/kind
    sudo mv /tmp/kind /usr/local/bin/kind
    ok "kind installed"
}

create_cluster() {
    log "Recreating kind cluster '${CLUSTER_NAME}'..."
    kind delete cluster --name "${CLUSTER_NAME}" 2>/dev/null || true
    kind create cluster --name "${CLUSTER_NAME}" --wait=180s

    mkdir -p "$HOME/.kube"
    kind get kubeconfig --name "${CLUSTER_NAME}" --internal=false > "$HOME/.kube/config"
}

verify_cluster() {
    log "Verifying cluster connectivity..."
    if ! kubectl get nodes >/dev/null 2>&1; then
        err "Cluster failed to start properly"
        docker logs "${CLUSTER_NAME}-control-plane" || true
        exit 1
    fi
    ok "Kind cluster ready"
    kubectl cluster-info
    kubectl get nodes
    kubectl get pods --all-namespaces
}

install_pip_dependencies() {
    log "Installing Python dependencies (ML & Orchestration)..."
    # Using a list to make it easier to manage/read
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
    ok "Pip dependencies installed"
}

# ── Main ─────────────────────────────────────────────────────────────
main() {
    banner "Setup Script"
    print_requirements
    detect_arch
    wait_for_docker
    install_kind
    create_cluster
    verify_cluster
    install_pip_dependencies

    ok "Setup complete."
}

# Only run main when executed directly, allows for sourcing functions
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
