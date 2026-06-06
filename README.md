# Distributed Workload PoC

**Scalable orchestration for distributed ETL, ML Training, Hyperparameter Tuning and ML Inference workloads**

## Overview

PoC demonstrating distributed workload orchestration using **Ray** as the primary compute framework with **Prefect** for workflow orchestration, supporting cloud-native deployments (Kubernetes).

## Backlog

Tracked future improvements and planned work items are maintained in [BACKLOG.md](./BACKLOG.md).

## Quick Start

### Docker Compose

Docker is the default runtime.

```bash
export RUNTIME=compose

# 1. Start platform
make start

# 2. Dashboards
make open-ray
make open-mlflow
make open-prefect

# 3. Run workloads (Ray)
make etl-ray
make train-ray
make tune-ray

# OR run via Prefect
make run-pipeline-prefect
make run-etl-prefect

# 4. Deploy inference API server
make serve-start-ray
make test-inference-api

# OR via Prefect
make deploy-model-prefect

# Stop inference API server
make serve-stop-ray

# 5. Stop platform
make stop
```

### Kubernetes (Kind)

Same commands. Just switch runtime.

```sh
export RUNTIME=k8s

# 1. Start platform
make start

# 2. Port-forward dashboards (separate terminal)
make forward

# 3. Dashboards
make open-ray
make open-mlflow
make open-prefect

# 4. Run workloads (Ray)
make etl-ray
make train-ray
make tune-ray

# OR Prefect workflows
make run-pipeline-prefect
make run-etl-prefect

# 5. Deploy inference API server
make serve-start-ray
make test-inference-api

# OR via Prefect
make deploy-model-prefect

# Stop inference API server
make serve-stop-ray

# 6. Stop platform
make stop
```

## Available Commands
```bash
Distributed Workload PoC

Current runtime: compose

Usage:
  make <target> [RUNTIME=compose|k8s]

  help                           Show available targets
  open-ray                       Open Ray dashboard
  open-mlflow                    Open MLflow dashboard
  open-prefect                   Open Prefect dashboard
  test-inference-api             Test inference API
  start                          Start platform
  stop                           Stop platform
  restart                        Restart platform
  logs                           Follow platform logs
  rebuild                        Rebuild images (docker only)
  forward                        Port-forward dashboards (k8s only)
  etl-ray                        Run ETL workload via Ray
  train-ray                      Run training workload via Ray
  tune-ray                       Run hyperparameter tuning via Ray
  serve-start-ray                Deploy inference service
  serve-stop-ray                 Stop inference service
  run-pipeline-prefect           Run ML pipeline via Prefect
  deploy-model-prefect           Deploy model via Prefect
  run-etl-prefect                Run ETL via Prefect
  deploy-schedules-prefect       Deploy Prefect schedules
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
│  ┌──────────────┐  ┌─────────────┐                          │
│  │ Docker       │  │ Kubernetes  │                          │
│  │ Compose      │  │ (Kind/EKS/  │                          │
│  │ (Local Dev)  │  │ GKE/AKS)    │                          │
│  └──────────────┘  └─────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

### Production Deployment

For production workloads, use **managed Kubernetes services** with [KubeRay Operator](https://docs.ray.io/en/latest/cluster/kubernetes/index.html):

- **AWS:** [Amazon EKS](https://aws.amazon.com/eks/)
- **GCP:** [Google GKE](https://cloud.google.com/kubernetes-engine)
- **Azure:** [Azure AKS](https://azure.microsoft.com/en-us/products/kubernetes-service)

**Advantages:**
- Auto-scaling (nodes + pods)
- Self-healing & high availability
- Managed control plane
- Production-grade observability

See [Deployment Comparison](./docs/deployment-comparison.md) for detailed guidance.
