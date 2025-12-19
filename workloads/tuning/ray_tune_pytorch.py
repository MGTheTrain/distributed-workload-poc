#!/usr/bin/env python3
"""
Distributed Hyperparameter Tuning with Ray Tune and MLflow
Finds optimal hyperparameters using AsyncHyperBandScheduler and Bayesian optimization
"""
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any

import boto3
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torch.optim import Adam

import ray
from ray import tune
from ray.air import session
from ray.tune.schedulers import AsyncHyperBandScheduler
from ray.tune.search.hyperopt import HyperOptSearch
from ray.tune.search import ConcurrencyLimiter
from ray.train import Checkpoint
import pyarrow.fs as pafs
import mlflow
import traceback
from hyperopt import hp
import numpy as np

# Configuration

class Config:
    """Training and infrastructure configuration"""
    
    # Paths
    DATA_DIR = Path(os.getenv("DATA_DIR", "/workspace/data"))
    MODEL_DIR = Path(os.getenv("MODEL_DIR", str(DATA_DIR / "models")))
    
    # MLflow
    MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    MLFLOW_EXPERIMENT = "ray-tune-pytorch"
    
    # Ray
    RAY_ADDRESS = os.getenv("RAY_ADDRESS", "ray://localhost:6379")
    
    # S3 / LocalStack
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "test")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
    AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "http://localstack:4566")
    S3_BUCKET = os.getenv("S3_BUCKET", "mlflow-artifacts")
    
    # Tuning
    NUM_SAMPLES = 5  # Limit memory usage
    MAX_CONCURRENT_TRIALS = 3  # Limit parallel trials to prevent OOM
    MAX_EPOCHS = 5   # Max epochs per trial
    GRACE_PERIOD = 3  # Min epochs before early stopping
    REDUCTION_FACTOR = 2


# Configure environment for MLflow S3 access
os.environ.update({
    "AWS_ACCESS_KEY_ID": Config.AWS_ACCESS_KEY_ID,
    "AWS_SECRET_ACCESS_KEY": Config.AWS_SECRET_ACCESS_KEY,
    "AWS_DEFAULT_REGION": Config.AWS_DEFAULT_REGION,
    "MLFLOW_S3_ENDPOINT_URL": Config.AWS_S3_ENDPOINT_URL,
})

# Set MLflow tracking
mlflow.set_tracking_uri(Config.MLFLOW_TRACKING_URI)
mlflow.set_experiment(Config.MLFLOW_EXPERIMENT)


# S3 Utilities

def get_s3_client():
    """Create configured S3 client for LocalStack"""
    return boto3.client(
        's3',
        endpoint_url=Config.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
        region_name=Config.AWS_DEFAULT_REGION
    )


def ensure_bucket_exists(s3_client, bucket: str) -> None:
    """Ensure S3 bucket exists, create if it doesn't"""
    try:
        s3_client.head_bucket(Bucket=bucket)
    except Exception:
        s3_client.create_bucket(Bucket=bucket)
        print(f" Created S3 bucket: {bucket}")

def ensure_mnist_downloaded(data_dir: Path) -> bool:
    """Download MNIST once if not present, with fallback mirrors"""
    # NOTE: Production like pattern (private/public storage system (e.g. HF, S3) → local cache → download fallback)
    mnist_dir = data_dir / "MNIST" / "raw"

    if mnist_dir.exists():
        print(" MNIST already downloaded")
        return False
    
    print(" Downloading MNIST dataset...")
    
    # Try downloading with retries and error handling
    max_retries = 3
    for attempt in range(max_retries):
        try:
            datasets.MNIST(root=str(data_dir), train=True, download=True)
            datasets.MNIST(root=str(data_dir), train=False, download=True)
            print(" MNIST downloaded successfully")
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Download attempt {attempt + 1} failed: {e}")
                print(f"   Retrying... ({attempt + 2}/{max_retries})")
                # Clean up partial downloads
                raw_dir = data_dir / "MNIST" / "raw"
                if raw_dir.exists():
                    shutil.rmtree(raw_dir)
                    raw_dir.mkdir(parents=True)
            else:
                print(f" All download attempts failed")
                raise RuntimeError(
                    f"Failed to download MNIST after {max_retries} attempts. "
                    "The official MNIST mirror may be down. "
                    "Please download manually from https://github.com/pytorch/vision/issues/3549"
                ) from e

# Model

class ConvNet(nn.Module):
    """Simple CNN for MNIST classification
    
    Architecture:
    - Conv1: 1→32 channels, 3x3 kernel → 26x26 feature maps
    - Pool1: 2x2 max pooling → 13x13 feature maps
    - Conv2: 32→64 channels, 3x3 kernel → 11x11 feature maps  
    - Pool2: 2x2 max pooling → 5x5 feature maps
    - Flatten: 64 * 5 * 5 = 1600 features (hardcoded for MNIST 28x28 input)
    - FC1: 1600 → 128
    - FC2: 128 → 10 (classes)
    
    NOTE: The 1600 is hardcoded based on MNIST's 28x28 input size.
    For variable input sizes, consider dynamic inference or adaptive pooling.
    """
    
    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3)
        self.fc1 = nn.Linear(1600, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.conv1(x))
        x = F.max_pool2d(x, 2)
        x = F.relu(self.conv2(x))
        x = F.max_pool2d(x, 2)
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)


# Tuning Function

def tune_mnist(config: Dict[str, Any]) -> None:
    """
    Training function for hyperparameter tuning
    Each trial trains with different hyperparameters
    """
    
    # Extract hyperparameters
    lr = config["lr"]
    batch_size = config["batch_size"]
    seed = config.get("seed", 42)

    # Set seeds for reproducibility
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    
    # Data transforms
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])
    
    # Load datasets
    train_dataset = datasets.MNIST(
        root=str(Config.DATA_DIR),
        train=True,
        download=False,
        transform=transform
    )
    test_dataset = datasets.MNIST(
        root=str(Config.DATA_DIR),
        train=False,
        download=False,
        transform=transform
    )
    
    # Data loaders
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        pin_memory=torch.cuda.is_available()
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=torch.cuda.is_available()
    )
    
    # Model setup
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ConvNet()
    model.to(device)
    
    optimizer = Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    # Get trial info
    trial_name = session.get_trial_name()  
    trial_id = session.get_trial_id()
    
    # Log trial_id as MLflow parameter (once, not per epoch)
    run_id = config.get("mlflow_run_id")
    if run_id:
        client = mlflow.tracking.MlflowClient()
        try:
            client.log_param(run_id, f"{trial_name}/trial_id", trial_id)  # Log as param
        except Exception:
            pass  # Ignore if already logged
    
    # Training loop
    for epoch in range(Config.MAX_EPOCHS):
        # Train
        model.train()
        train_loss = 0.0
        for data, target in train_loader:
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
        
        avg_train_loss = train_loss / len(train_loader)
        
        # Evaluate
        model.eval()
        test_loss = 0.0
        correct = 0
        with torch.no_grad():
            for data, target in test_loader:
                data, target = data.to(device), target.to(device)
                output = model(data)
                test_loss += criterion(output, target).item()
                pred = output.argmax(dim=1, keepdim=True)
                correct += pred.eq(target.view_as(pred)).sum().item()
        
        avg_test_loss = test_loss / len(test_loader)
        accuracy = correct / len(test_dataset)
        
        # Save checkpoint every 2 epochs
        checkpoint = None
        if (epoch + 1) % 2 == 0:
            checkpoint_dir = tempfile.mkdtemp(prefix="tune_ckpt_")
            torch.save(
                model.state_dict(),
                os.path.join(checkpoint_dir, "model.pt")
            )
            checkpoint = Checkpoint.from_directory(checkpoint_dir)
        
        # Report to Tune (with training_iteration for AsyncHyperBand)
        tune.report(
            {
                "accuracy": accuracy,
                "test_loss": avg_test_loss,
                "train_loss": avg_train_loss,
                "epoch": epoch,
                "training_iteration": epoch + 1  # For AsyncHyperBand scheduler
            },
            checkpoint=checkpoint
        )

        # MLflow logging
        if run_id:
            try:
                # Create metrics dict with ONLY numeric values
                numeric_metrics = {
                    "accuracy": float(accuracy),
                    "train_loss": float(avg_train_loss),
                    "test_loss": float(avg_test_loss),
                    "completed_epoch": int(epoch + 1)  # 1-indexed for clarity
                }
                
                # Log each metric
                for metric_key, metric_value in numeric_metrics.items():
                    metric_name = f"{trial_name}/{metric_key}"
                    client.log_metric(run_id, metric_name, metric_value, step=epoch)
            except Exception as e:
                # Don't fail trial if MLflow logging fails
                print(f"  MLflow logging error (non-fatal): {e}")

# Main

def main() -> None:
    """Launch hyperparameter tuning with MLflow tracking"""
    
    print("\n" + "="*70)
    print(" HYPERPARAMETER TUNING WITH RAY TUNE + MLFLOW")
    print("="*70 + "\n")
    
    # Connect to Ray cluster first
    ray.init(address=Config.RAY_ADDRESS, ignore_reinit_error=True)
    print(f"🚀 Connected to Ray cluster: {Config.RAY_ADDRESS}")
    
    # Detect GPU availability safely
    @ray.remote
    def detect_gpu():
        return torch.cuda.is_available()
    
    use_gpu = ray.get(detect_gpu.remote())
    num_cpus = os.cpu_count() or 2
    
    if use_gpu:
        print(f" GPU detected - will use GPU acceleration")
    else:
        print(f" CPU-only mode")
    print(f" CPU cores: {num_cpus}\n")
    
    # Initialize S3
    s3_client = get_s3_client()
    ensure_bucket_exists(s3_client, Config.S3_BUCKET)
    
    # Download MNIST once
    ensure_mnist_downloaded(Config.DATA_DIR)
    
    # Start MLflow run for the entire tuning session
    with mlflow.start_run(run_name="hyperparameter_tuning") as parent_run:
        parent_run_id = parent_run.info.run_id
        
        # Log tuning configuration
        mlflow.log_params({
            "num_samples": Config.NUM_SAMPLES,
            "max_epochs": Config.MAX_EPOCHS,
            "grace_period": Config.GRACE_PERIOD,
            "framework": "pytorch",
            "model": "ConvNet",
            "dataset": "MNIST",
            "use_gpu": use_gpu,
        })
        
        # Define hyperparameter search space
        search_space = {
            "lr": tune.loguniform(1e-4, 1e-1),
            "batch_size": tune.choice([32, 64, 128]),
            "seed": 42,  # Fixed for reproducibility
            "mlflow_run_id": parent_run_id,
        }
        
        # AsyncHyperBandScheduler for early stopping of unpromising trials
        scheduler = AsyncHyperBandScheduler(
            time_attr="training_iteration", 
            metric="accuracy",
            mode="max",
            max_t=Config.MAX_EPOCHS,
            grace_period=Config.GRACE_PERIOD,
            reduction_factor=Config.REDUCTION_FACTOR
        )
        
        # HyperOpt search for Bayesian optimization
        # Automatically limits concurrency to prevent OOM
        try:
            # Define search space for HyperOpt
            hyperopt_search_space = {
                "lr": hp.loguniform("lr", np.log(1e-4), np.log(1e-1)),
                "batch_size": hp.choice("batch_size", [32, 64, 128]),
                "seed": 42,
                "mlflow_run_id": parent_run_id,
            }
            
            search_alg = HyperOptSearch(
                space=hyperopt_search_space,
                metric="accuracy",
                mode="max",
                n_initial_points=Config.MAX_CONCURRENT_TRIALS,  # Random search first
            )
            
            # Wrap with ConcurrencyLimiter to control parallel trials
            search_alg = ConcurrencyLimiter(
                search_alg,
                max_concurrent=Config.MAX_CONCURRENT_TRIALS
            )
            
            # Override search_space since HyperOpt has its own
            search_space = None
            
            print(" Using HyperOpt for Bayesian optimization")
            
        except ImportError:
            print("  HyperOpt not available, using random search")
            print("   Install with: pip install hyperopt")
            search_alg = None
            # Keep original search_space for random search
        
        # S3 storage for results
        s3_fs = pafs.S3FileSystem(
            endpoint_override=Config.AWS_S3_ENDPOINT_URL,
            access_key=Config.AWS_ACCESS_KEY_ID,
            secret_key=Config.AWS_SECRET_ACCESS_KEY,
            region=Config.AWS_DEFAULT_REGION
        )
        
        # Configure Tune
        tuner = tune.Tuner(
            tune.with_resources(
                tune_mnist,
                resources={"cpu": 2, "gpu": 1 if use_gpu else 0}
            ),
            param_space=search_space or {},  # Empty if using HyperOpt's space
            tune_config=tune.TuneConfig(
                num_samples=Config.NUM_SAMPLES,
                scheduler=scheduler,
                search_alg=search_alg,  # HyperOpt or None (random)
            ),
            run_config=tune.RunConfig(
                name="mnist_tuning",
                storage_path=f"{Config.S3_BUCKET}/tune_results",
                storage_filesystem=s3_fs,
            ),
        )
        
        print(f" Starting tuning with {Config.NUM_SAMPLES} trials...\n")
        print(f" Configuration:")
        print(f"   Total trials: {Config.NUM_SAMPLES}")
        print(f"   Max concurrent: {Config.MAX_CONCURRENT_TRIALS}")
        print(f"   Max epochs per trial: {Config.MAX_EPOCHS}")
        print(f"   Grace period: {Config.GRACE_PERIOD}")
        print(f"   Resources per trial: 2 CPU, {1 if use_gpu else 0} GPU")
        print(f"\n Search space:")
        print(f"   Learning rate: 1e-4 to 1e-1 (log-uniform)")
        print(f"   Batch size: [32, 64, 128]")
        print()
        
        results = tuner.fit()
        
        print(f"\n Tuning completed!")
        print(f"   Total trials run: {len(results)}")
        print(f"   Results available: {results is not None}")
        
        if len(results) == 0:
            raise RuntimeError("No trials completed successfully!")
        
        # Get best result
        best_result = results.get_best_result(metric="accuracy", mode="max")
        
        # Log best hyperparameters to MLflow
        mlflow.log_params({
            f"best_{k}": v for k, v in best_result.config.items()
        })
        mlflow.log_metrics({
            "best_accuracy": best_result.metrics["accuracy"],
            "best_test_loss": best_result.metrics["test_loss"],
        })
        
        # Log best checkpoint to MLflow
        if best_result.checkpoint:
            with best_result.checkpoint.as_directory() as checkpoint_dir:
                local_checkpoint_dir = tempfile.mkdtemp(prefix="mlflow_best_")
                
                for file in Path(checkpoint_dir).rglob("*"):
                    if file.is_file():
                        dest = Path(local_checkpoint_dir) / file.relative_to(checkpoint_dir)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file, dest)
                
                mlflow.log_artifacts(local_checkpoint_dir, "best_model")
                shutil.rmtree(local_checkpoint_dir)
        
        # Log all trials summary
        df = results.get_dataframe()
        df.to_csv("/tmp/tune_results.csv", index=False)
        mlflow.log_artifact("/tmp/tune_results.csv", "trial_results")
        
        # Summary
        print("\n" + "="*70)
        print(" TUNING COMPLETE")
        print("="*70)
        print(f" Best hyperparameters:")
        print(f"   Learning rate: {best_result.config['lr']:.6f}")
        print(f"   Batch size: {best_result.config['batch_size']}")
        print(f"\n Best performance:")
        print(f"   Accuracy: {best_result.metrics['accuracy']:.2%}")
        print(f"   Test loss: {best_result.metrics['test_loss']:.4f}")
        print(f"\n MLflow: {Config.MLFLOW_TRACKING_URI}")
        print(f"  S3: s3://{Config.S3_BUCKET}/tune_results")
        print("="*70 + "\n")
        
        print(" Tip: Use these hyperparameters in your training script!")
        print(f"   Config.LEARNING_RATE = {best_result.config['lr']:.6f}")
        print(f"   Config.BATCH_SIZE = {best_result.config['batch_size']}\n")
        
        ray.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n Tuning failed: {e}")
        
        # Log failure to MLflow if possible
        try:
            mlflow.log_param("status", "failed")
            mlflow.log_param("error", str(e))
        except Exception:
            pass
        
        traceback.print_exc()
        raise