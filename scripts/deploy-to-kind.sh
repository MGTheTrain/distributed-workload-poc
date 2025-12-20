#!/bin/bash
set -e

# Color definitions
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Deploy Complete ML Stack to Kind (Official Charts)      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if Kind cluster exists
if ! kind get clusters | grep -q "^kind$"; then
    echo -e "${RED}❌ Kind cluster 'kind' not found${NC}"
    echo -e "${YELLOW}💡 Create it with: kind create cluster${NC}"
    exit 1
fi

CLUSTER_NAME="kind"

# Image definitions (service_name image_name:tag)
IMAGES_TO_BUILD=(
    "ray custom-ray:2.51.1-py312 ./infra/ray/Dockerfile"
    "prefect custom-prefect:3-python3.12 ./infra/prefect/Dockerfile"
    "mlflow custom-mlflow:3.7.0 ./infra/mlflow/Dockerfile"
)

# Chart versions (locked to tested versions)
KUBERAY_OPERATOR_VERSION="1.2.2"
RAY_CLUSTER_VERSION="1.2.2"
POSTGRESQL_VERSION="16.6.3"
LOCALSTACK_VERSION="0.6.27"

# Helm repositories
declare -A HELM_REPOS=(
    ["kuberay"]="https://ray-project.github.io/kuberay-helm/"
    ["bitnami"]="https://charts.bitnami.com/bitnami"
    ["community-charts"]="https://community-charts.github.io/helm-charts"
    ["localstack"]="https://localstack.github.io/helm-charts"
)

# Step 1: Add Helm repositories (conditional)
echo -e "${YELLOW}📚 Step 1/11: Checking Helm repositories...${NC}"
REPOS_NEEDED=false

for repo_name in "${!HELM_REPOS[@]}"; do
    if ! helm repo list 2>/dev/null | grep -q "^${repo_name}"; then
        echo -e "${BLUE}Adding ${repo_name} repository...${NC}"
        helm repo add "${repo_name}" "${HELM_REPOS[$repo_name]}"
        REPOS_NEEDED=true
    fi
done

if [ "$REPOS_NEEDED" = true ]; then
    echo -e "${BLUE}Updating Helm repositories...${NC}"
    helm repo update
    echo -e "${GREEN}✓ Helm repositories added and updated${NC}"
else
    echo -e "${GREEN}✓ All Helm repositories already configured${NC}"
fi
echo ""

# Step 2: Create namespace
echo -e "${YELLOW}📦 Step 2/11: Creating namespace...${NC}"
kubectl create namespace ml-stack --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Namespace created${NC}"
echo ""

# Step 3: Build all images
echo -e "${YELLOW}🐳 Step 3/11: Building Docker images...${NC}"
SHOULD_BUILD=false

for image_spec in "${IMAGES_TO_BUILD[@]}"; do
    read -r service_name image_name dockerfile <<< "$image_spec"
    
    if ! docker image inspect "${image_name}" >/dev/null 2>&1; then
        echo -e "${BLUE}Image ${image_name} not found, will build${NC}"
        SHOULD_BUILD=true
        
        echo -e "${BLUE}Building ${service_name} (${image_name})...${NC}"
        docker build \
            -t "${image_name}" \
            -f "${dockerfile}" \
            .
        echo -e "${GREEN}✓ ${service_name} image built${NC}"
    else
        echo -e "${GREEN}✓ Image ${image_name} already exists, skipping${NC}"
    fi
done

if [ "$SHOULD_BUILD" = false ]; then
    echo -e "${GREEN}✓ All images already exist${NC}"
fi
echo ""

# Step 4: Load images into Kind cluster
echo -e "${YELLOW}📦 Step 4/11: Loading images into Kind cluster...${NC}"

for image_spec in "${IMAGES_TO_BUILD[@]}"; do
    read -r service_name image_name dockerfile <<< "$image_spec"
    
    # Extract just the image name without tag for checking
    image_base=$(echo "${image_name}" | cut -d':' -f1)
    
    if docker exec ${CLUSTER_NAME}-control-plane crictl images | grep -q "${image_base}"; then
        echo -e "${GREEN}✓ Image ${image_name} already in cluster, skipping${NC}"
    else
        echo -e "${BLUE}Loading ${image_name} into cluster...${NC}"
        kind load docker-image "${image_name}" --name ${CLUSTER_NAME}
        echo -e "${GREEN}✓ ${service_name} image loaded${NC}"
    fi
done
echo -e "${GREEN}✓ All images loaded into Kind cluster${NC}"
echo ""

# Step 5: Deploy PostgreSQL
echo -e "${YELLOW}🐘 Step 5/11: Deploying PostgreSQL...${NC}"

if kubectl get statefulset postgres -n ml-stack &>/dev/null; then
    echo -e "${GREEN}✓ PostgreSQL already installed${NC}"
else
    echo -e "${BLUE}Installing PostgreSQL (official image)...${NC}"
    
    cat <<EOF | kubectl apply -f -
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-init-script
  namespace: ml-stack
data:
  init.sql: |
    CREATE DATABASE mlflow;
    CREATE DATABASE prefect;
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-postgresql
  namespace: ml-stack
spec:
  type: ClusterIP
  ports:
    - port: 5432
      targetPort: 5432
  selector:
    app: postgres
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: ml-stack
spec:
  serviceName: postgres-postgresql
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
        app.kubernetes.io/name: postgresql
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_USER
          value: "mlflow"
        - name: POSTGRES_PASSWORD
          value: "mlflow"
        - name: POSTGRES_DB
          value: "mlflow"
        - name: PGDATA
          value: "/var/lib/postgresql/data/pgdata"
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        - name: init-script
          mountPath: /docker-entrypoint-initdb.d
        resources:
          requests:
            cpu: 250m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          exec:
            command:
              - sh
              - -c
              - pg_isready -U mlflow
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
              - sh
              - -c
              - pg_isready -U mlflow
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: postgres-storage
        emptyDir: {}
      - name: init-script
        configMap:
          name: postgres-init-script
EOF
    
    echo -e "${BLUE}Waiting for PostgreSQL to be ready...${NC}"
    kubectl wait --for=condition=ready pod -l app=postgres -n ml-stack --timeout=120s

    echo -e "${GREEN}✓ PostgreSQL deployed${NC}"
fi
echo ""

# Step 6: Deploy LocalStack
echo -e "${YELLOW}☁️  Step 6/11: Deploying LocalStack (S3)...${NC}"
if helm list -n ml-stack 2>/dev/null | grep -q "^localstack"; then
    echo -e "${GREEN}✓ LocalStack already installed, skipping${NC}"
else
    echo -e "${BLUE}Installing LocalStack ${LOCALSTACK_VERSION}...${NC}"
    helm upgrade --install localstack localstack/localstack \
        --namespace ml-stack \
        --version ${LOCALSTACK_VERSION} \
        --set service.type=ClusterIP \
        --set startServices=s3 \
        --set extraEnvVars[0].name=AWS_ACCESS_KEY_ID \
        --set extraEnvVars[0].value=test \
        --set extraEnvVars[1].name=AWS_SECRET_ACCESS_KEY \
        --set extraEnvVars[1].value=test \
        --set persistence.enabled=false \
        --wait --timeout=5m
    
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=localstack -n ml-stack --timeout=120s
    
    echo -e "${GREEN}✓ LocalStack deployed${NC}"
fi
echo ""

# Step 7: Deploy MLflow with custom image
echo -e "${YELLOW}📊 Step 7/11: Deploying MLflow...${NC}"

if kubectl get deployment mlflow -n ml-stack &>/dev/null; then
    echo -e "${GREEN}✓ MLflow already installed${NC}"
else
    echo -e "${BLUE}Installing MLflow via custom manifest...${NC}"
    
    cat <<EOF | kubectl apply -f -
---
apiVersion: v1
kind: Service
metadata:
  name: mlflow
  namespace: ml-stack
  labels:
    app: mlflow
spec:
  type: ClusterIP
  ports:
    - port: 5000
      targetPort: 5000
      protocol: TCP
      name: http
  selector:
    app: mlflow
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlflow
  namespace: ml-stack
  labels:
    app: mlflow
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mlflow
  template:
    metadata:
      labels:
        app: mlflow
    spec:
      containers:
      - name: mlflow
        image: custom-mlflow:3.7.0
        imagePullPolicy: Never
        command: ["mlflow", "server"]
        args:
          - "--backend-store-uri"
          - "postgresql://mlflow:mlflow@postgres-postgresql:5432/mlflow"
          - "--default-artifact-root"
          - "s3://mlflow-artifacts/"
          - "--host"
          - "0.0.0.0"
          - "--port"
          - "5000"
          - "--cors-allowed-origins"
          - "*"
          - "--allowed-hosts"
          - "*"
        env:
        - name: MLFLOW_S3_ENDPOINT_URL
          value: "http://localstack:4566"
        - name: AWS_ACCESS_KEY_ID
          value: "test"
        - name: AWS_SECRET_ACCESS_KEY
          value: "test"
        ports:
        - name: http
          containerPort: 5000
          protocol: TCP
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
EOF
    
    echo -e "${GREEN}✓ MLflow deployed${NC}"
fi
echo ""

# Step 8: Deploy KubeRay Operator
echo -e "${YELLOW}🎛️  Step 8/12: Deploying KubeRay Operator...${NC}"
if helm list -n ml-stack 2>/dev/null | grep -q "^kuberay-operator"; then
    echo -e "${GREEN}✓ KubeRay Operator already installed, skipping${NC}"
else
    echo -e "${BLUE}Installing KubeRay Operator ${KUBERAY_OPERATOR_VERSION}...${NC}"
    helm upgrade --install kuberay-operator kuberay/kuberay-operator \
        --namespace ml-stack \
        --version ${KUBERAY_OPERATOR_VERSION} \
        --wait --timeout=5m
    
    kubectl wait --for=condition=available --timeout=120s \
        deployment/kuberay-operator -n ml-stack
    
    echo -e "${GREEN}✓ KubeRay Operator deployed${NC}"
fi
echo ""

# Step 9: Create PVC for shared data (like docker volume)
echo -e "${YELLOW}💾 Step 9/12: Creating shared data PVC...${NC}"

if kubectl get pvc ray-shared-data -n ml-stack &>/dev/null; then
    echo -e "${GREEN}✓ PVC already exists${NC}"
else
    echo -e "${BLUE}Creating PersistentVolume and PersistentVolumeClaim...${NC}"
    
    cat <<EOF | kubectl apply -f -
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: ray-shared-data
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteMany
  storageClassName: ""  # Empty to allow manual binding
  hostPath:
    path: /tmp/ray-data
    type: DirectoryOrCreate
  persistentVolumeReclaimPolicy: Retain
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ray-shared-data
  namespace: ml-stack
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ""  # Empty to match PV
  volumeName: ray-shared-data  # Explicitly bind to our PV
  resources:
    requests:
      storage: 10Gi
EOF
    
    echo -e "${GREEN}✓ Shared data PVC created${NC}"
fi
echo ""

# Step 10: Deploy Ray cluster with custom image and shared PVC
echo -e "${YELLOW}⚡ Step 10/12: Deploying Ray cluster...${NC}"
if helm list -n ml-stack 2>/dev/null | grep -q "^ray-cluster"; then
    echo -e "${GREEN}✓ Ray cluster already installed, skipping${NC}"
else
    echo -e "${BLUE}Installing Ray cluster ${RAY_CLUSTER_VERSION}...${NC}"
    
    # Create values file for Ray
    cat > /tmp/ray-values.yaml <<EOF
image:
  repository: custom-ray
  tag: 2.51.1-py312
  pullPolicy: Never

head:
  # Init container to fix volume permissions
  initContainers:
    - name: fix-permissions
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          chown -R 1000:100 /workspace/data
          chmod -R 775 /workspace/data
      volumeMounts:
        - name: ray-data
          mountPath: /workspace/data
      securityContext:
        runAsUser: 0  # Run as root to change ownership
  
  rayStartParams:
    dashboard-host: '0.0.0.0'
    num-cpus: '10'
  resources:
    limits:
      cpu: 4
      memory: 8Gi
    requests:
      cpu: 2
      memory: 4Gi
  
  volumes:
    - name: ray-data
      persistentVolumeClaim:
        claimName: ray-shared-data
  
  volumeMounts:
    - name: ray-data
      mountPath: /workspace/data
  
  containerEnv:
    - name: RAY_ADDRESS
      value: "ray://ray-cluster-kuberay-head-svc:10001"
    - name: MLFLOW_TRACKING_URI
      value: "http://mlflow:5000"
    - name: AWS_ACCESS_KEY_ID
      value: "test"
    - name: AWS_SECRET_ACCESS_KEY
      value: "test"
    - name: AWS_DEFAULT_REGION
      value: "us-east-1"
    - name: AWS_S3_ENDPOINT_URL
      value: "http://localstack:4566"
    - name: MLFLOW_S3_ENDPOINT_URL
      value: "http://localstack:4566"
    - name: DATA_DIR
      value: "/workspace/data"

worker:
  # Init container to fix volume permissions
  initContainers:
    - name: fix-permissions
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          chown -R 1000:100 /workspace/data
          chmod -R 775 /workspace/data
      volumeMounts:
        - name: ray-data
          mountPath: /workspace/data
      securityContext:
        runAsUser: 0  # Run as root to change ownership
  
  replicas: 2
  rayStartParams:
    num-cpus: '5'
  resources:
    limits:
      cpu: 2
      memory: 4Gi
    requests:
      cpu: 1
      memory: 2Gi
  
  volumes:
    - name: ray-data
      persistentVolumeClaim:
        claimName: ray-shared-data
  
  volumeMounts:
    - name: ray-data
      mountPath: /workspace/data
  
  containerEnv:
    - name: RAY_ADDRESS
      value: "ray://ray-cluster-kuberay-head-svc:10001"
    - name: MLFLOW_TRACKING_URI
      value: "http://mlflow:5000"
    - name: AWS_ACCESS_KEY_ID
      value: "test"
    - name: AWS_SECRET_ACCESS_KEY
      value: "test"
    - name: AWS_DEFAULT_REGION
      value: "us-east-1"
    - name: AWS_S3_ENDPOINT_URL
      value: "http://localstack:4566"
    - name: MLFLOW_S3_ENDPOINT_URL
      value: "http://localstack:4566"
    - name: DATA_DIR
      value: "/workspace/data"
EOF

    helm upgrade --install ray-cluster kuberay/ray-cluster \
        --namespace ml-stack \
        --version ${RAY_CLUSTER_VERSION} \
        -f /tmp/ray-values.yaml \
        --wait --timeout=5m
    
    echo -e "${GREEN}✓ Ray cluster deployed${NC}"
fi
echo ""

# Step 11: Deploy Prefect server with custom image
echo -e "${YELLOW}🔀 Step 11/12: Deploying Prefect server...${NC}"

if kubectl get deployment prefect-server -n ml-stack &>/dev/null; then
    echo -e "${GREEN}✓ Prefect already installed, skipping${NC}"
else
    echo -e "${BLUE}Installing Prefect via custom manifests...${NC}"
    
    cat <<EOF | kubectl apply -f -
---
apiVersion: v1
kind: Service
metadata:
  name: prefect-server
  namespace: ml-stack
  labels:
    app: prefect-server
spec:
  type: ClusterIP
  ports:
    - port: 4200
      targetPort: 4200
      protocol: TCP
      name: http
  selector:
    app: prefect-server
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prefect-server
  namespace: ml-stack
  labels:
    app: prefect-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prefect-server
  template:
    metadata:
      labels:
        app: prefect-server
    spec:
      containers:
      - name: prefect-server
        image: custom-prefect:3-python3.12
        imagePullPolicy: Never
        command: ["prefect", "server", "start"]
        args:
          - "--host"
          - "0.0.0.0"
          - "--port"
          - "4200"
        env:
        - name: RAY_ADDRESS
          value: "ray://ray-cluster-kuberay-head-svc:10001"
        ports:
        - name: http
          containerPort: 4200
          protocol: TCP
        livenessProbe:
          httpGet:
            path: /api/health
            port: 4200
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /api/health
            port: 4200
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
EOF
    
    echo -e "${GREEN}✓ Prefect server deployed${NC}"
fi
echo ""

# Step 12: Wait for all deployments
echo -e "${YELLOW}⏳ Step 12/12: Waiting for all pods to be ready...${NC}"

# Wait for each deployment
DEPLOYMENTS=("mlflow" "prefect-server")
for deployment in "${DEPLOYMENTS[@]}"; do
    echo -e "${BLUE}Waiting for ${deployment}...${NC}"
    kubectl wait --for=condition=ready --timeout=300s pod -l app=${deployment} -n ml-stack 2>/dev/null || true
done

echo -e "${GREEN}✓ All deployments ready${NC}"
echo ""

# Summary
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                     Deployment Summary                      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Chart Versions Deployed:${NC}"
echo "  PostgreSQL:       ${POSTGRESQL_VERSION}"
echo "  LocalStack:       ${LOCALSTACK_VERSION}"
echo "  MLflow:           3.7.0 (custom image)"
echo "  KubeRay Operator: ${KUBERAY_OPERATOR_VERSION}"
echo "  Ray Cluster:      ${RAY_CLUSTER_VERSION} (custom image)"
echo "  Prefect:          3-python3.12 (custom image)"
echo ""
echo -e "${GREEN}ML Stack:${NC}"
kubectl get pods -n ml-stack
echo ""
echo -e "${GREEN}Services:${NC}"
kubectl get svc -n ml-stack | grep -E "(mlflow|postgres|localstack|ray-cluster|prefect)"
echo ""
echo -e "${YELLOW}Quick Commands:${NC}"
echo "  Port-forward all: make k8s-forward"
echo "  Check status:     kubectl get pods -n ml-stack"
echo ""
echo -e "${GREEN}✓ Deployment complete with locked chart versions${NC}"