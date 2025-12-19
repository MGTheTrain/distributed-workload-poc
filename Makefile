.PHONY: help compose-start compose-stop compose-rebuild compose-logs compose-clean \
        compose-etl-ray compose-train-ray compose-tune-ray \
        compose-serve-start-ray test-inference-api compose-serve-stop-ray \
		compose-run-pipeline-prefect compose-deploy-model-prefect compose-run-etl-prefect \
		compose-deploy-schedules-prefect \
		open-ray open-mlflow k8s-deploy k8s-clean k8s-forward k8s-etl-ray

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
	@open http://localhost:5000 2>/dev/null || xdg-open http://localhost:5000 2>/dev/null || echo "Open http://localhost:5000"

open-prefect: ## [Common] Open Prefect Dashboard
	@echo " Opening Prefect Dashboard..."
	@open http://localhost:4200 2>/dev/null || xdg-open http://localhost:4200 2>/dev/null || echo "Open http://localhost:4200"

test-inference-api: ## [Common] Test inference service API
	@echo " Testing inference api..."
	@python ./scripts/test-inference-api.py

# Docker Compose Targets

compose-start: ## [Compose] Start all services
	@echo " Starting Ray cluster..."
	@docker compose up -d
	@echo " Waiting for services..."
	@sleep 10
	@echo " Services started"

compose-stop: ## [Compose] Stop all services
	@docker compose down

compose-rebuild: ## [Compose] Rebuild all images
	@echo "🔨 Rebuilding all images..."
	@docker compose build
	@echo " Rebuild complete"

compose-logs: ## [Compose] Show logs
	@docker compose logs -f

compose-clean: ## [Compose] Stop and remove everything
	@docker compose down -v
	@docker system prune -f

# ETL Workloads

compose-etl-ray: ## [Compose] Run Ray ETL (dashboard logs)
	@echo " Submitting Ray ETL job..."
	@docker compose exec ray-head ray job submit -- python /workspace/workloads/etl/ray_etl_pipeline.py

# ML Training Workloads

compose-train-ray: ## [Compose] Run PyTorch training (dashboard logs)
	@echo " Submitting training job..."
	@docker compose exec ray-head ray job submit -- python /workspace/workloads/training/ray_train_pytorch.py

# ML Tuning Workloads

compose-tune-ray: ## [Compose] Run hyperparameter tuning (dashboard logs)
	@echo " Submitting tuning job..."
	@docker compose exec ray-head ray job submit -- python /workspace/workloads/tuning/ray_tune_pytorch.py

# ML Inference Workloads

compose-serve-start-ray: ## [Compose] Deploy inference service
	@echo " Deploying inference service with Ray Serve..."
	@docker compose exec ray-head bash -c "ray job submit -- bash -c 'cd /workspace/workloads/inference && serve deploy serve_config.yaml'"

compose-serve-stop-ray: ## [Compose] Stop inference service
	@echo " Stopping inference service..."
	@docker compose exec ray-head serve shutdown

# Prefect Orchestrated Workloads

compose-run-pipeline-prefect: ## [Compose] Run ML training pipeline (Prefect)
	@echo " Running ML training pipeline via Prefect..."
	@docker compose exec prefect python /workspace/workloads/orchestration/workload_orchestrator_prefect.py run-pipeline

compose-deploy-model-prefect: ## [Compose] Deploy model (Prefect)
	@echo " Deploying model via Prefect..."
	@docker compose exec prefect python /workspace/workloads/orchestration/workload_orchestrator_prefect.py deploy-model

compose-run-etl-prefect: ## [Compose] Run ETL only (Prefect)
	@echo " Running ETL via Prefect..."
	@docker compose exec prefect python /workspace/workloads/orchestration/workload_orchestrator_prefect.py run-etl

compose-deploy-schedules-prefect: ## [Compose] Deploy Prefect schedules
	@echo " Deploying Prefect schedules..."
	@docker compose exec prefect python /workspace/workloads/orchestration/workload_orchestrator_prefect.py deploy-schedules
	
# Kubernetes Targets

k8s-deploy: ## [K8s] Deploy to Kind cluster
	@echo " Deploying to Kind cluster..."
	@bash scripts/deploy-to-kind.sh

k8s-clean: ## [K8s] Cleanup Kind cluster
	@echo " Cleaning up Kind cluster..."
	@bash scripts/cleanup-kind.sh

k8s-forward: ## [K8s] Port-forward dashboards
	@echo " Port-forwarding services..."
	@bash scripts/port-forward-in-kind.sh

k8s-etl-ray: ## [K8s] Run Ray ETL on K8s
	@echo " Running Ray ETL on Kubernetes..."
	@kubectl exec -n ray deploy/ray-cluster-kuberay-head -- python /workspace/workloads/etl/ray_etl_pipeline.py
