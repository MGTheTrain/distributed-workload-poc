# Distributed Workload PoC — developer commands

export PROJECT_ROOT   ?= $(CURDIR)

COMPOSE_FILE ?= infra/compose/docker-compose.yml
COMPOSE      := docker compose -f $(COMPOSE_FILE)

RAY_HEAD_POD = $$(kubectl get pod -n ml-stack -l ray.io/node-type=head -o name | head -1)
PREFECT_POD = $$(kubectl get pod -n ml-stack -l app=prefect-server -o name | head -1)

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Common targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## \[Common\]/ {printf "  \033[35m%-27s\033[0m %s\n", $$1, substr($$2, 10)}' $(MAKEFILE_LIST)
	@echo ''
	@echo 'Docker Compose targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^compose-[a-zA-Z_-]+:.*?## \[Compose\]/ {printf "  \033[36m%-27s\033[0m %s\n", $$1, substr($$2, 11)}' $(MAKEFILE_LIST)
	@echo ''
	@echo 'Kubernetes targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^k8s-[a-zA-Z_-]+:.*?## \[K8s\]/ {printf "  \033[33m%-27s\033[0m %s\n", $$1, substr($$2, 7)}' $(MAKEFILE_LIST)

# Common Targets

open-ray: ## [Common] Open Ray Dashboard
	@echo " Opening Ray Dashboard..."
	@open http://localhost:8265 2>/dev/null || xdg-open http://localhost:8265 2>/dev/null || echo "Open http://localhost:8265"

open-mlflow: ## [Common] Open MLflow Dashboard
	@echo " Opening MLflow Dashboard..."
	@open http://localhost:5001 2>/dev/null || xdg-open http://localhost:5001 2>/dev/null || echo "Open http://localhost:5001"

open-prefect: ## [Common] Open Prefect Dashboard
	@echo " Opening Prefect Dashboard..."
	@open http://localhost:4200 2>/dev/null || xdg-open http://localhost:4200 2>/dev/null || echo "Open http://localhost:4200"

test-inference-api: ## [Common] Test inference service API
	@echo " Testing inference api..."
	@python ./scripts/test-inference-api.py

# Docker Compose Targets

compose-start: ## [Compose] Start all services
	@$(COMPOSE) up -d

compose-stop: ## [Compose] Stop all services
	@$(COMPOSE) down

compose-restart: compose-stop compose-start ## [Compose] Restart all services

compose-rebuild: ## [Compose] Rebuild all images
	@echo "🔨 Rebuilding all images..."
	@$(COMPOSE) build
	@echo " Rebuild complete"

compose-logs: ## [Compose] Show logs
	@$(COMPOSE) logs -f

compose-clean: ## [Compose] Stop and remove everything
	@$(COMPOSE) down -v
	@docker system prune -f

# ETL Workloads

compose-etl-ray: ## [Compose] Run ETL (dashboard logs)
	@echo " Submitting ETL job..."
	@$(COMPOSE) exec ray-head ray job submit -- python /workspace/workloads/etl/ray_etl_pipeline.py

# ML Training Workloads

compose-train-ray: ## [Compose] Run PyTorch training (dashboard logs)
	@echo " Submitting training job..."
	@$(COMPOSE) exec ray-head ray job submit -- python /workspace/workloads/training/ray_train_pytorch.py

# ML Tuning Workloads

compose-tune-ray: ## [Compose] Run hyperparameter tuning (dashboard logs)
	@echo " Submitting tuning job..."
	@$(COMPOSE) exec ray-head ray job submit -- python /workspace/workloads/tuning/ray_tune_pytorch.py

# ML Inference Workloads

compose-serve-start-ray: ## [Compose] Deploy inference service
	@echo " Deploying inference service..."
	@$(COMPOSE) exec ray-head bash -c "ray job submit -- bash -c 'cd /workspace/workloads/inference && serve deploy serve_config.yaml'"

compose-serve-stop-ray: ## [Compose] Stop inference service
	@echo " Stopping inference service..."
	@$(COMPOSE) exec ray-head serve shutdown --yes

# Prefect Orchestrated Workloads

compose-run-pipeline-prefect: ## [Compose] Run ML training pipeline (Prefect)
	@echo " Running ML training pipeline via Prefect..."
	@$(COMPOSE) exec prefect python /workspace/workloads/orchestration/workload_orchestrator_prefect.py run-pipeline

compose-deploy-model-prefect: ## [Compose] Deploy model (Prefect)
	@echo " Deploying model via Prefect..."
	@$(COMPOSE) exec prefect python /workspace/workloads/orchestration/workload_orchestrator_prefect.py deploy-model

compose-run-etl-prefect: ## [Compose] Run ETL only (Prefect)
	@echo " Running ETL via Prefect..."
	@$(COMPOSE) exec prefect python /workspace/workloads/orchestration/workload_orchestrator_prefect.py run-etl

compose-deploy-schedules-prefect: ## [Compose] Deploy Prefect schedules
	@echo " Deploying Prefect schedules..."
	@$(COMPOSE) exec prefect python /workspace/workloads/orchestration/workload_orchestrator_prefect.py deploy-schedules

# Kubernetes Targets

k8s-deploy: ## [K8s] Deploy to Kind cluster
	@echo " Deploying to Kind cluster..."
	@bash scripts/deploy-to-kind.sh

k8s-clean: ## [K8s] Cleanup Kind cluster
	@echo " Cleaning up Kind cluster..."
	@bash scripts/cleanup-kind.sh

k8s-redeploy: ## [K8s] Uninstall + install (full reset) PoC k8s resources on the kind cluster
	@bash scripts/cleanup-kind.sh
	@bash scripts/deploy-to-kind.sh

k8s-forward: ## [K8s] Port-forward dashboards
	@echo " Port-forwarding services..."
	@bash scripts/port-forward-in-kind.sh

# Workload Execution on K8s

k8s-etl-ray: ## [K8s] Run ETL on K8s
	@echo " Submitting ETL on Kubernetes..."
	@kubectl exec -n ml-stack $(RAY_HEAD_POD) -- \
		bash -c "ray job submit -- python /workspace/workloads/etl/ray_etl_pipeline.py"

k8s-train-ray: ## [K8s] Run PyTorch training on K8s
	@echo " Submitting training job on Kubernetes..."
	@kubectl exec -n ml-stack $(RAY_HEAD_POD) -- \
		bash -c "ray job submit -- python /workspace/workloads/training/ray_train_pytorch.py"

k8s-tune-ray: ## [K8s] Run hyperparameter tuning on K8s
	@echo " Submitting tuning job on Kubernetes..."
	@kubectl exec -n ml-stack $(RAY_HEAD_POD) -- \
		bash -c "ray job submit -- python /workspace/workloads/tuning/ray_tune_pytorch.py"

# ML Inference Workloads on K8s

k8s-serve-start-ray: ## [K8s] Deploy inference service on K8s
	@echo " Deploying inference service..."
	@kubectl exec -n ml-stack $(RAY_HEAD_POD) -- \
		bash -c "cd /workspace/workloads/inference && serve deploy serve_config.yaml"
	@echo ""
	@echo " Inference service deployed!"
	@echo ""
	@echo " Starting port-forward to Ray Serve (port 8000)..."
	@echo "   Press Ctrl+C to stop port-forwarding"
	@echo "   Test endpoint: http://localhost:8000"
	@echo "   Test inference API: make test-inference-api"
	@echo ""
	@kubectl port-forward -n ml-stack svc/ray-cluster-head-svc 8000:8000

k8s-serve-stop-ray: ## [K8s] Stop inference service on K8s
	@echo " Stopping inference service..."
	@kubectl exec -n ml-stack $(RAY_HEAD_POD) -- \
		bash -c "serve shutdown --yes"

# Prefect Orchestrated Workloads on K8s

k8s-run-pipeline-prefect: ## [K8s] Run ML pipeline via Prefect on K8s
	@echo " Running ML pipeline via Prefect on Kubernetes..."
	@kubectl exec -n ml-stack $(PREFECT_POD) -- \
		bash -c "python /workspace/workloads/orchestration/workload_orchestrator_prefect.py run-pipeline"

k8s-deploy-model-prefect: ## [K8s] Deploy model via Prefect on K8s
	@echo " Deploying model via Prefect on Kubernetes..."
	@kubectl exec -n ml-stack $(PREFECT_POD) -- \
		bash -c "python /workspace/workloads/orchestration/workload_orchestrator_prefect.py deploy-model"
	@echo ""
	@echo " Inference service deployed!"
	@echo ""
	@echo " Starting port-forward to Ray Serve (port 8000)..."
	@echo "   Press Ctrl+C to stop port-forwarding"
	@echo "   Test endpoint: http://localhost:8000"
	@echo "   Test inference API: make test-inference-api"
	@echo ""
	@kubectl port-forward -n ml-stack svc/ray-cluster-head-svc 8000:8000

k8s-run-etl-prefect: ## [K8s] Run ETL only via Prefect on K8s
	@echo " Running ETL via Prefect on Kubernetes..."
	@kubectl exec -n ml-stack $(PREFECT_POD) -- \
		bash -c "python /workspace/workloads/orchestration/workload_orchestrator_prefect.py run-etl"

k8s-deploy-schedules-prefect: ## [K8s] Deploy Prefect schedules on K8s
	@echo " Deploying Prefect schedules on Kubernetes..."
	@kubectl exec -n ml-stack $(PREFECT_POD) -- \
		bash -c "python /workspace/workloads/orchestration/workload_orchestrator_prefect.py deploy-schedules"
