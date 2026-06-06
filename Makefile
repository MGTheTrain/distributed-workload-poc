# Distributed Workload PoC — developer commands

export PROJECT_ROOT ?= $(CURDIR)

RUNTIME ?= compose
NAMESPACE ?= ml-stack

COMPOSE_FILE ?= infra/compose/docker-compose.yml
COMPOSE      := docker compose -f $(COMPOSE_FILE)

RAY_RUNTIME_ENV_JSON ?= {}

RAY_HEAD_POD = $$(kubectl get pod -n $(NAMESPACE) -l ray.io/node-type=head -o name | head -1)
PREFECT_POD  = $$(kubectl get pod -n $(NAMESPACE) -l app=prefect-server -o name | head -1)

# Runtime abstraction

ifeq ($(RUNTIME),compose)

RAY_EXEC     = $(COMPOSE) exec ray-head
PREFECT_EXEC = $(COMPOSE) exec prefect

else ifeq ($(RUNTIME),k8s)

RAY_EXEC     = kubectl exec -n $(NAMESPACE) $(RAY_HEAD_POD) --
PREFECT_EXEC = kubectl exec -n $(NAMESPACE) $(PREFECT_POD) --

else

$(error Unsupported RUNTIME='$(RUNTIME)' (expected compose|k8s))

endif

# Help

help: ## Show available targets
	@echo ''
	@echo 'Distributed Workload PoC'
	@echo ''
	@echo 'Current runtime: $(RUNTIME)'
	@echo ''
	@echo 'Usage:'
	@echo '  make <target> [RUNTIME=compose|k8s]'
	@echo ''
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z0-9_-]+:.*?## / {printf "  \033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Common

open-ray: ## Open Ray dashboard
	@open http://localhost:8265 2>/dev/null || \
	 xdg-open http://localhost:8265 2>/dev/null || \
	 echo "Open http://localhost:8265"

open-mlflow: ## Open MLflow dashboard
	@open http://localhost:5001 2>/dev/null || \
	 xdg-open http://localhost:5001 2>/dev/null || \
	 echo "Open http://localhost:5001"

open-prefect: ## Open Prefect dashboard
	@open http://localhost:4200 2>/dev/null || \
	 xdg-open http://localhost:4200 2>/dev/null || \
	 echo "Open http://localhost:4200"

test-inference-api: ## Test inference API
	@pytest scripts/test_inference_api.py -v

# Runtime lifecycle

start: ## Start platform
ifeq ($(RUNTIME),compose)
	@$(COMPOSE) up -d --build
else
	@bash scripts/deploy-to-kind.sh
endif

stop: ## Stop platform
ifeq ($(RUNTIME),compose)
	@$(COMPOSE) down
else
	@bash scripts/cleanup-kind.sh
endif

restart: stop start ## Restart platform

logs: ## Follow platform logs
ifeq ($(RUNTIME),compose)
	@$(COMPOSE) logs -f
else
	@echo "Use kubectl logs for specific workloads:"
	@kubectl get pods -n $(NAMESPACE)
endif

rebuild: ## Rebuild images (docker only)
ifeq ($(RUNTIME),compose)
	@$(COMPOSE) build
else
	@echo "Rebuild not applicable for k8s runtime"
endif

forward: ## Port-forward dashboards (k8s only)
ifeq ($(RUNTIME),k8s)
	@bash scripts/port-forward-in-kind.sh
else
	@echo "Docker runtime exposes dashboards directly"
endif

forward-bg: ## Background port-forward dashboards (k8s only; PID -> /tmp/dwp-pf.pid)
ifeq ($(RUNTIME),k8s)
	@bash scripts/port-forward-in-kind.sh > /tmp/dwp-pf.log 2>&1 & echo $$! > /tmp/dwp-pf.pid
	@echo "Port-forwards started in background (see /tmp/dwp-pf.log)"
else
	@echo "forward-bg is k8s-only"
endif

forward-serve: ## Forward Ray Serve to localhost:8000 (k8s only; non-blocking)
ifeq ($(RUNTIME),k8s)
	@kubectl port-forward -n $(NAMESPACE) svc/ray-cluster-head-svc 8000:8000 \
	  > /tmp/dwp-serve-pf.log 2>&1 & echo $$! > /tmp/dwp-serve-pf.pid
	@for i in $$(seq 1 15); do \
	  curl -sf http://localhost:8000/ >/dev/null 2>&1 && break || sleep 2; \
	done
	@echo "Ray Serve forwarded to localhost:8000"
else
	@echo "Compose exposes localhost:8000 directly; nothing to forward"
endif

forward-stop: ## Stop background port-forwards (k8s only)
ifeq ($(RUNTIME),k8s)
	@if [ -f /tmp/dwp-pf.pid ]; then kill $$(cat /tmp/dwp-pf.pid) 2>/dev/null || true; rm -f /tmp/dwp-pf.pid; fi
	@# also drop any stray serve-port forward started by forward-serve
	@if [ -f /tmp/dwp-serve-pf.pid ]; then kill $$(cat /tmp/dwp-serve-pf.pid) 2>/dev/null || true; rm -f /tmp/dwp-serve-pf.pid; fi
else
	@echo "forward-stop is k8s-only"
endif

wait-healthy: ## Block until Ray + MLflow + Prefect respond (max 120s)
	@echo " Waiting for stack to be healthy..."
	@for i in $$(seq 1 60); do \
	  ray=$$(curl -sS -o /dev/null -w '%{http_code}' http://localhost:8265 2>/dev/null || echo 000); \
	  mlf=$$(curl -sS -o /dev/null -w '%{http_code}' http://localhost:5001/health 2>/dev/null || echo 000); \
	  pfe=$$(curl -sS -o /dev/null -w '%{http_code}' http://localhost:4200/api/health 2>/dev/null || echo 000); \
	  echo "  [$$i] ray=$$ray mlflow=$$mlf prefect=$$pfe"; \
	  if [ "$$ray" = "200" ] && [ "$$mlf" = "200" ] && [ "$$pfe" = "200" ]; then \
	    echo " ✓ stack is healthy"; exit 0; \
	  fi; \
	  sleep 2; \
	done; \
	echo " ✗ stack did not become healthy in 120s"; exit 1

k8s-wait-pods: ## Block until platform pods are Ready (k8s only)
ifeq ($(RUNTIME),k8s)
	@echo "Waiting for pods to be Ready..."
	@kubectl wait --for=condition=ready pod \
	  -l ray.io/node-type=head -n $(NAMESPACE) --timeout=300s
	@kubectl wait --for=condition=ready pod \
	  -l app=mlflow -n $(NAMESPACE) --timeout=300s
	@kubectl wait --for=condition=ready pod \
	  -l app=prefect-server -n $(NAMESPACE) --timeout=300s
endif

# Ray workloads

etl-ray: ## Run ETL workload via Ray
	@echo "Submitting ETL workload..."
	@$(RAY_EXEC) bash -c \
		'ray job submit --runtime-env-json='\''$(RAY_RUNTIME_ENV_JSON)'\'' -- python /workspace/workloads/etl/ray_etl_pipeline.py'

train-ray: ## Run training workload via Ray
	@echo "Submitting training workload..."
	@$(RAY_EXEC) bash -c \
	  'ray job submit --runtime-env-json='\''$(RAY_RUNTIME_ENV_JSON)'\'' -- python /workspace/workloads/training/ray_train_pytorch.py'

tune-ray: ## Run hyperparameter tuning via Ray
	@echo "Submitting tuning workload..."
	@$(RAY_EXEC) bash -c \
   	  'ray job submit --runtime-env-json='\''$(RAY_RUNTIME_ENV_JSON)'\'' -- python /workspace/workloads/tuning/ray_tune_pytorch.py'

# Ray Serve

serve-start-ray: ## Deploy inference service
	@echo "Deploying inference service..."
	@$(RAY_EXEC) bash -c \
	  "cd /workspace/workloads/inference && serve deploy serve_config.yaml"
ifeq ($(RUNTIME),k8s)
	@echo "Inference service deployed; run 'make forward-serve' to reach localhost:8000"
endif

serve-stop-ray: ## Stop inference service
	@$(RAY_EXEC) bash -c "serve shutdown --yes"

# Prefect workloads

run-pipeline-prefect: ## Run ML pipeline via Prefect
	@echo "Running ML pipeline..."
	@$(PREFECT_EXEC) bash -c \
	  "python /workspace/workloads/orchestration/workload_orchestrator_prefect.py run-pipeline"

deploy-model-prefect: ## Deploy model via Prefect
	@echo "Deploying model..."
	@$(PREFECT_EXEC) bash -c \
	  "python /workspace/workloads/orchestration/workload_orchestrator_prefect.py deploy-model"
ifeq ($(RUNTIME),k8s)
	@echo "Model deployed; run 'make forward-serve' to reach localhost:8000"
endif

run-etl-prefect: ## Run ETL via Prefect
	@echo "Running ETL..."
	@$(PREFECT_EXEC) bash -c \
	  "python /workspace/workloads/orchestration/workload_orchestrator_prefect.py run-etl"

deploy-schedules-prefect: ## Deploy Prefect schedules
	@echo "Deploying schedules..."
	@$(PREFECT_EXEC) bash -c \
	  "python /workspace/workloads/orchestration/workload_orchestrator_prefect.py deploy-schedules"
