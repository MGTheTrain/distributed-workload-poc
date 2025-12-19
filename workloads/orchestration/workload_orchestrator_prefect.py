#!/usr/bin/env python3
"""
Prefect orchestrated ML pipeline using Ray for distributed execution
Uses ray job submit CLI for simplicity
"""
import sys
import subprocess
from prefect import flow, task, serve


@task(name="submit-etl-job", retries=2)
def submit_etl_job():
    """Submit ETL pipeline to Ray cluster via CLI"""
    print(" Submitting ETL job to Ray...")
    
    result = subprocess.run(
        [
            "ray", "job", "submit",
            "--",
            "python", "/workspace/workloads/etl/ray_etl_pipeline.py"
        ],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f" ETL completed successfully")
        print(f"\n{result.stdout}")
        return {"status": "success", "output": result.stdout}
    else:
        print(f" ETL failed:")
        print(f"\n{result.stderr}")
        raise Exception(f"ETL job failed: {result.stderr}")


@task(name="submit-training-job", retries=2)
def submit_training_job():
    """Submit training job to Ray cluster via CLI"""
    print("🎓 Submitting training job to Ray...")
    
    result = subprocess.run(
        [
            "ray", "job", "submit",
            "--",
            "python", "/workspace/workloads/training/ray_train_pytorch.py"
        ],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f" Training completed successfully")
        print(f"\n{result.stdout}")
        return {"status": "success", "output": result.stdout}
    else:
        print(f" Training failed:")
        print(f"\n{result.stderr}")
        raise Exception(f"Training job failed: {result.stderr}")


@task(name="submit-tuning-job", retries=1)
def submit_tuning_job():
    """Submit hyperparameter tuning to Ray cluster via CLI"""
    print(" Submitting tuning job to Ray...")
    
    result = subprocess.run(
        [
            "ray", "job", "submit",
            "--",
            "python", "/workspace/workloads/tuning/ray_tune_pytorch.py"
        ],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f" Tuning completed successfully")
        print(f"\n{result.stdout}")
        return {"status": "success", "output": result.stdout}
    else:
        print(f"⚠️  Tuning job status: failed")
        print(f"\n{result.stderr}")
        # Don't fail the whole pipeline if tuning fails
        return {"status": "failed", "error": result.stderr}


@task(name="deploy-model", retries=3)
def deploy_model():
    """Deploy model to Ray Serve"""
    print(" Deploying model to Ray Serve...")
    
    result = subprocess.run(
        [
            "ray", "job", "submit",
            "--",
            "bash", "-c",
            "cd /workspace/workloads/inference && serve deploy serve_config.yaml"
        ],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f" Model deployed successfully")
        return {"deployed": True, "endpoint": "http://ray-head:8000"}
    else:
        raise Exception(f" Deployment failed: {result.stderr}")

@flow(name="ml-pipeline-full", log_prints=True)
def ml_pipeline():
    """
    Complete ML pipeline: ETL → Tuning → Training
    Orchestrated by Prefect, executed on Ray via CLI
    """
    print("\n" + "="*70)
    print(" STARTING ML TRAINING PIPELINE")
    print("="*70 + "\n")
    
    # 1. Run ETL pipeline (Prepare data)
    etl_result = submit_etl_job()
    
    # 2. Hyperparameter tuning (Find best params)
    tuning_result = submit_tuning_job()

    # 3. Train model (Use best params)
    training_result = submit_training_job()
    
    print("\n" + "="*70)
    print(" TRAINING PIPELINE COMPLETED")
    print("="*70)
    print(f"   ETL: {etl_result['status']}")
    print(f"   Tuning: {tuning_result['status']}")
    print(f"   Training: {training_result['status']}")
    print("="*70 + "\n")
    
    return {
        "etl": etl_result,
        "tuning": tuning_result,
        "training": training_result
    }


@flow(name="ml-deployment", log_prints=True)
def ml_deployment():
    """
    Deployment flow: Deploy model to Ray Serve
    Run separately after validating training results
    """
    print("\n" + "="*70)
    print(" DEPLOYING MODEL TO RAY SERVE")
    print("="*70 + "\n")
    
    deployment_result = deploy_model()
    
    print(f" Endpoint: {deployment_result['endpoint']}")
    print("="*70 + "\n")
    
    return deployment_result


@flow(name="etl-only", log_prints=True)
def etl_only():
    """Standalone ETL flow"""
    print("\n" + "="*70)
    print(" RUNNING ETL ONLY")
    print("="*70 + "\n")
    
    result = submit_etl_job()
    
    print("\n" + "="*70)
    print(" ETL COMPLETED")
    print("="*70 + "\n")
    
    return result

def deploy_schedules():
    """
    Deploy Prefect schedules using Prefect 3.x API
    """
    print(" Deploying Prefect schedules...\n")
    
    # Deploy flows with schedules
    serve(
        ml_pipeline.to_deployment(
            name="ml-pipeline-daily",
            interval=86400,  # Daily (24 hours in seconds)
            tags=["ml", "production", "daily"]
        ),
        etl_only.to_deployment(
            name="etl-hourly",
            interval=3600,  # Hourly (1 hour in seconds)
            tags=["etl", "hourly"]
        )
    )


if __name__ == "__main__":
    # CLI interface
    if len(sys.argv) < 2:
        print("Usage: python workload_orchestrator.py [COMMAND]")
        print("\nCommands:")
        print("  run-pipeline      Run full ML training pipeline (ETL → Tune → Train)")
        print("  run-etl           Run ETL only")
        print("  deploy-model      Deploy model to Ray Serve")
        print("  deploy-schedules  Deploy scheduled workflows")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "run-pipeline":
        ml_pipeline()
    elif command == "run-etl":
        etl_only()
    elif command == "deploy-model":
        ml_deployment()
    elif command == "deploy-schedules":
        deploy_schedules()
    else:
        print(f" Unknown command: {command}")
        sys.exit(1)