# Distributed Workload PoC

![WIP](https://img.shields.io/badge/status-WIP-yellow)

**Scalable orchestration for distributed ETL, ML Training, Hyperparameter Tuning and ML Inference workloads**

## Overview

PoC demonstrating distributed workload orchestration using **Ray** as the primary compute framework with **Prefect** for workflow orchestration, supporting traditional HPC environments (SLURM) and cloud-native deployments (Kubernetes). 

## Quick Start

Choose your deployment environment based on your needs:

---

### Local Development (Docker Compose)

**Prerequisites:** Docker + Docker Compose. Consider existing [dev container](.devcontainer/kind/devcontainer.json) for local setup

#### Option 1: Direct Ray Execution
```bash
# 1. Start distributed cluster
make compose-start

# 2. Run workloads directly on Ray
make compose-etl-ray            # Distributed ETL
make compose-train-ray          # Distributed ML training
make compose-tune-ray           # Distributed hyperparameter tuning
make compose-serve-start-ray    # Inference serving
make test-inference-api         # Test inference service API

# 3. View dashboards
make open-ray                   # Ray Dashboard (http://localhost:8265)
make open-mlflow                # MLflow UI (http://localhost:5000)

# 4. Stop and cleanup
make compose-stop
make compose-clean
```

#### Option 2: Prefect-Orchestrated Workflows
```bash
# 1. Start distributed cluster (includes Prefect)
make compose-start

# 2. Run orchestrated ML pipeline
make compose-run-pipeline-prefect   # Full pipeline: ETL → Tune → Train
make compose-run-etl-prefect        # Distributed ETL only
make compose-deploy-model-prefect   # Deploy model / Inference serving
make test-inference-api             # Test inference service API

# 3. View dashboards
make open-prefect               # Prefect UI (http://localhost:4200)
make open-ray                   # Ray Dashboard (http://localhost:8265)
make open-mlflow                # MLflow UI (http://localhost:5000)

# 4. Schedule workflows (optional)
make compose-deploy-schedules-prefect  # Deploy daily/hourly schedules

# 5. Stop and cleanup
make compose-stop
make compose-clean
```

---

### Production-like Environment (Kubernetes)

**Prerequisites:** Docker + Kind cluster. Consider existing [dev container](.devcontainer/kind/devcontainer.json) for local setup

#### Option 1: Direct Ray Execution on Kubernetes
```bash
# 1. Deploy complete ML stack to Kind cluster
make k8s-deploy

# 2. Port-forward dashboards in separate terminal (required for access)
make k8s-forward

# 3. Run workloads directly on Ray cluster
make k8s-etl-ray                # Distributed ETL
make k8s-train-ray              # Distributed ML training
make k8s-tune-ray               # Distributed hyperparameter tuning
make k8s-serve-start-ray        # Inference serving
make test-inference-api         # Test inference service API

# 4. View dashboards
make open-ray                   # Ray Dashboard (http://localhost:8265)
make open-mlflow                # MLflow UI (http://localhost:5000)

# 5. Cleanup
make k8s-clean
```

#### Option 2: Prefect-Orchestrated Workflows on Kubernetes
```bash
# 1. Deploy complete ML stack to Kind cluster
make k8s-deploy

# 2. Port-forward dashboards in separate terminal (required for access)
make k8s-forward

# 3. Run orchestrated ML pipeline
make k8s-run-pipeline-prefect   # Full pipeline: ETL → Tune → Train
make k8s-run-etl-prefect        # Distributed ETL only
make k8s-deploy-model-prefect   # Deploy model / Inference serving
make test-inference-api         # Test inference service API

# 4. View dashboards
make open-prefect               # Prefect UI (http://localhost:4200)
make open-ray                   # Ray Dashboard (http://localhost:8265)
make open-mlflow                # MLflow UI (http://localhost:5000)

# 5. Schedule workflows (optional)
make k8s-deploy-schedules-prefect  # Deploy daily/hourly schedules

# 6. Cleanup
make k8s-clean
```

## Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                  Workflow Orchestration                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Prefect Server                                      │   │
│  │  • Workflow scheduling (cron, intervals, events)     │   │
│  │  • DAG management & dependencies                     │   │
│  │  • Retry logic & error handling                      │   │
│  │  • Task monitoring & observability                   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
                    (submits jobs via CLI)
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              Distributed Compute Engine                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Ray Cluster (Head + Workers)                       │   │
│  │   • Job submission & scheduling                      │   │
│  │   • Distributed execution (ETL, Train, Tune)         │   │
│  │   • Resource management (CPU/GPU allocation)         │   │
│  │   • Model serving (Ray Serve)                        │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
                    (logs metrics & artifacts)
                              ↓
┌─────────────────────────────────────────────────────────────┐
│            Experiment Tracking & Storage                    │
│  ┌────────────────────┐  ┌──────────────────────────────┐   │
│  │  MLflow Server     │  │  S3 / LocalStack             │   │
│  │  • Run tracking    │  │  • Model checkpoints         │   │
│  │  • Metrics logging │  │  • Training artifacts        │   │
│  │  • Model registry  │  │  • ETL results               │   │
│  └────────────────────┘  └──────────────────────────────┘   │
│  ┌────────────────────┐                                     │
│  │  PostgreSQL        │                                     │
│  │  • MLflow metadata │                                     │
│  └────────────────────┘                                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 Deployment Targets                          │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────────┐    │
│  │ Docker       │  │ Kubernetes  │  │  SLURM           │    │
│  │ Compose      │  │ (Kind)      │  │  (HPC clusters)  │    │
│  └──────────────┘  └─────────────┘  └──────────────────┘    │
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
  open-prefect                Open Prefect Dashboard
  test-inference-api          Test inference service API

Docker Compose targets:
  compose-start               Start all services
  compose-stop                Stop all services
  compose-rebuild             Rebuild all images
  compose-logs                Show logs
  compose-clean               Stop and remove everything
  compose-etl-ray             Run ETL (dashboard logs)
  compose-train-ray           Run PyTorch training (dashboard logs)
  compose-tune-ray            Run hyperparameter tuning (dashboard logs)
  compose-serve-start-ray     Deploy inference service
  compose-serve-stop-ray      Stop inference service
  compose-run-pipeline-prefect Run ML training pipeline (Prefect)
  compose-deploy-model-prefect Deploy model (Prefect)
  compose-run-etl-prefect     Run ETL only (Prefect)
  compose-deploy-schedules-prefect Deploy Prefect schedules

Kubernetes targets:
  k8s-deploy                  Deploy to Kind cluster
  k8s-clean                   Cleanup Kind cluster
  k8s-forward                 Port-forward dashboards
  k8s-etl-ray                 Run ETL on K8s
  k8s-train-ray               Run PyTorch training on K8s
  k8s-tune-ray                Run hyperparameter tuning on K8s
  k8s-serve-start-ray         Deploy inference service on K8s
  k8s-serve-stop-ray          Stop inference service on K8s
  k8s-run-pipeline-prefect    Run ML pipeline via Prefect on K8s
  k8s-deploy-model-prefect    Deploy model via Prefect on K8s
  k8s-run-etl-prefect         Run ETL only via Prefect on K8s
  k8s-deploy-schedules-prefect Deploy Prefect schedules on K8s
```