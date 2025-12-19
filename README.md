# Distributed Workload PoC

![WIP](https://img.shields.io/badge/status-WIP-yellow)

**Scalable orchestration for distributed ETL, ML Training, Hyperparameter Tuning and ML Inference workloads**

## Overview

PoC demonstrating distributed workload orchestration using **Ray** as the primary compute framework with support for traditional HPC environments (SLURM) and cloud-native deployments (Kubernetes). 

## Quick Start

**Prerequisites:** Docker + Docker Compose
```bash
# 1. Start distributed cluster
make compose-start

# 2. Run workloads
make compose-etl-ray            # Distributed ETL
make compose-train-ray          # Distributed ML training
make compose-tune-ray           # Distributed ML tuning
make compose-serve-start-ray    # Inference serving
make test-inference-api         # Test inference service API

# 3. View dashboards
# Ray Dashboard: http://localhost:8265
make open-ray
# MLflow UI: http://localhost:5000
make open-mlflow

# 4. Stop and clear distributed cluster resources
make compose-stop
make compose-clean
```

## Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    Orchestration Layer                      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │   SLURM     │  │  Kubernetes  │  │  Docker Compose  │    │
│  │  Scheduler  │  │   (Kind)     │  │  (Local Dev)     │    │
│  └─────────────┘  └──────────────┘  └──────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              Distributed Computing Layer                    │
│  ┌──────────┐                                               │
│  │   Ray    │                                               │
│  │ Cluster  │                                               │
│  └──────────┘                                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 Workload Patterns                           │
│  • ETL Pipelines (data processing, transformations)         │
│  • ML Training (PyTorch, distributed training)              │
│  • ML Inference (Ray Serve, model serving)                  │
└─────────────────────────────────────────────────────────────┘
```

## Deployment Options

| Environment | Use Case | Command |
|------------|----------|---------|
| **Docker Compose** | Local dev, testing | `make compose-start` |
| **Kubernetes (Kind)** | Production-like testing | `make k8s-deploy` |
| **SLURM** | Traditional HPC clusters | `sbatch orchestration/slurm/ray_on_slurm.sh` |

## Available Commands
```bash
Usage: make [target]

Common targets:
  open-ray                    Open Ray Dashboard
  open-mlflow                 Open MLflow Dashboard
  test-inference-api          Test inference service API

Docker Compose targets:
  compose-start               Start all services
  compose-stop                Stop all services
  compose-rebuild             Rebuild all images
  compose-logs                Show logs
  compose-clean               Stop and remove everything
  compose-etl-ray             Run Ray ETL (dashboard logs)
  compose-train-ray           Run PyTorch training (dashboard logs)
  compose-tune-ray            Run hyperparameter tuning (dashboard logs)
  compose-serve-start-ray     Deploy inference service
  compose-serve-stop-ray      Stop inference service

Kubernetes targets:
  k8s-deploy                  Deploy to Kind cluster
  k8s-clean                   Cleanup Kind cluster
  k8s-forward                 Port-forward dashboards
  k8s-etl-ray                 Run Ray ETL on K8s
```

## Documentation

- [Architecture Overview](docs/architecture-overview.md) - System design & components
- [Troubleshooting Guide](docs/troubleshooting.md) - Common issues & solutions