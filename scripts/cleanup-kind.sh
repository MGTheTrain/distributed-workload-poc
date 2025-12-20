#!/bin/bash
set -e

echo "======================================================================"
echo "  Cleaning up Kind cluster"
echo "======================================================================"

echo ""
echo "  Removing Helm releases..."
helm uninstall ray-cluster -n ml-stack 2>/dev/null || echo "  Ray cluster not found"
helm uninstall kuberay-operator -n ml-stack 2>/dev/null || echo "  KubeRay operator not found"
helm uninstall localstack -n ml-stack 2>/dev/null || echo "  LocalStack not found"

echo ""
echo "  Deleting custom deployments..."
kubectl delete deployment mlflow prefect-server -n ml-stack 2>/dev/null || echo "  Custom deployments not found"

echo ""
echo "  Deleting StatefulSets..."
kubectl delete statefulset postgres -n ml-stack 2>/dev/null || echo "  PostgreSQL not found"

echo ""
echo "  Deleting PVCs..."
kubectl delete pvc ray-shared-data -n ml-stack 2>/dev/null || echo "  PVC not found"

echo ""
echo "  Deleting PVs..."
kubectl delete pv ray-shared-data 2>/dev/null || echo "  PV not found"

echo ""
echo "  Deleting namespace..."
kubectl delete namespace ml-stack --ignore-not-found=true

echo ""
echo " Waiting for cleanup..."
kubectl wait --for=delete namespace/ml-stack --timeout=60s 2>/dev/null || echo "  Namespace already deleted"

echo ""
echo "======================================================================"
echo " Cleanup complete"
echo "======================================================================"