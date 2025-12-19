#!/usr/bin/env python3
"""
Distributed PyTorch Training with Ray Train and MLflow
Handles GPU/CPU detection, S3 storage and robust checkpointing
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
from ray.train.torch import TorchTrainer
from ray.train import ScalingConfig, RunConfig, Checkpoint
import ray.train.torch
import mlflow
import pyarrow.fs as pafs
import traceback

# Configuration

class Config:
    """Training and infrastructure configuration"""
    
    # Paths
    DATA_DIR = Path(os.getenv("DATA_DIR", "/workspace/data"))
    MODEL_DIR = Path(os.getenv("MODEL_DIR", str(DATA_DIR / "models")))
    
    # MLflow
    MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    MLFLOW_EXPERIMENT = "ray-train-pytorch"
    
    # Ray
    RAY_ADDRESS = os.getenv("RAY_ADDRESS", "ray://localhost:6379")
    
    # S3 / LocalStack
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "test")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
    AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "http://localstack:4566")
    S3_BUCKET = os.getenv("S3_BUCKET", "mlflow-artifacts")
    
    # Training
    LEARNING_RATE = 0.001541 # Changed from 0.001 (tuning found 0.001541)
    BATCH_SIZE = 32 # Changed from 64 (tuning found 32 is optimal)
    EPOCHS = 10  # Keep at 10 (tuning used 5, but train more)
    NUM_WORKERS = 2


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


# Training

def train_func(config: Dict[str, Any]) -> None:
    """Distributed training function executed by each Ray worker"""
    
    # Extract config
    batch_size = config["batch_size"]
    lr = config["lr"]
    epochs = config["epochs"]
    seed = config.get("seed", 42)
    
    # MLflow config for live logging
    mlflow_tracking_uri = config.get("mlflow_tracking_uri")
    mlflow_run_id = config.get("mlflow_run_id")
    
    # Set seeds for reproducibility
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    
    # Worker info
    ctx = ray.train.get_context()
    rank = ctx.get_world_rank()
    world_size = ctx.get_world_size()
    is_rank_0 = rank == 0
    
    if is_rank_0:
        print(f"\n🎓 Training with {world_size} workers")
    print(f"   Worker Rank: {rank}")
    
    # Data transforms
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])
    
    # Download MNIST datasets (only once)
    if is_rank_0:
        ensure_mnist_downloaded(Config.DATA_DIR) 
    
    if world_size > 1:
        torch.distributed.barrier()
    
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
    
    # Data loaders with optimal settings
    train_loader = DataLoader(
        train_dataset, 
        batch_size=batch_size, 
        shuffle=True,
        num_workers=Config.NUM_WORKERS,
        pin_memory=torch.cuda.is_available()  # Faster GPU transfer
    )
    test_loader = DataLoader(
        test_dataset, 
        batch_size=batch_size, 
        shuffle=False,
        num_workers=Config.NUM_WORKERS,
        pin_memory=torch.cuda.is_available()
    )
    
    # Prepare for distributed training
    train_loader = ray.train.torch.prepare_data_loader(train_loader)
    test_loader = ray.train.torch.prepare_data_loader(test_loader)
    
    # Model setup
    model = ConvNet()
    model = ray.train.torch.prepare_model(model)
    optimizer = Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()
    
    # Training loop
    for epoch in range(epochs):
        # Sync distributed sampler
        if world_size > 1 and hasattr(train_loader, 'sampler'):
            train_loader.sampler.set_epoch(epoch)
        
        # Train
        model.train()
        train_loss = 0.0
        for data, target in train_loader:
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
        total = 0
        with torch.no_grad():
            for data, target in test_loader:
                output = model(data)
                test_loss += criterion(output, target).item()
                pred = output.argmax(dim=1, keepdim=True)
                correct += pred.eq(target.view_as(pred)).sum().item()
                total += target.size(0)  # Count actual samples seen
        
        # avg_test_loss = test_loss / len(test_loader) # NOTE: Calculation only valid for single node training
        # accuracy = correct / len(test_loader.dataset) # NOTE: Calculation only valid for single node training
        accuracy = correct / total 

        # For distributed training, aggregate metrics across workers
        if world_size > 1:
            # Convert to tensors
            train_loss_tensor = torch.tensor(avg_train_loss * len(train_loader), dtype=torch.float32)
            test_loss_tensor = torch.tensor(test_loss, dtype=torch.float32)
            correct_tensor = torch.tensor(correct, dtype=torch.float32)
            total_tensor = torch.tensor(total, dtype=torch.float32)

            # Sum across all workers
            torch.distributed.all_reduce(train_loss_tensor, op=torch.distributed.ReduceOp.SUM)
            torch.distributed.all_reduce(test_loss_tensor, op=torch.distributed.ReduceOp.SUM)
            torch.distributed.all_reduce(correct_tensor, op=torch.distributed.ReduceOp.SUM)
            torch.distributed.all_reduce(total_tensor, op=torch.distributed.ReduceOp.SUM)

            # Compute global averages
            avg_train_loss = train_loss_tensor.item() / (len(train_loader) * world_size)
            avg_test_loss = test_loss_tensor.item() / (len(test_loader) * world_size)
            accuracy = (correct_tensor / total_tensor).item()

        
        metrics = {
            "epoch": epoch,
            "train_loss": avg_train_loss,
            "test_loss": avg_test_loss,
            "accuracy": accuracy
        }
        
        # Dual logging strategy:
        # 1. Log to MLflow for live UI updates and historical tracking
        # 2. Log to Ray Train for distributed coordination and Result object
        if is_rank_0 and mlflow_tracking_uri and mlflow_run_id:
            try:
                mlflow.set_tracking_uri(mlflow_tracking_uri)
                # Use MlflowClient to avoid closing the parent run
                client = mlflow.tracking.MlflowClient()
                client.log_metric(mlflow_run_id, "train_loss", avg_train_loss, step=epoch)
                client.log_metric(mlflow_run_id, "test_loss", avg_test_loss, step=epoch)
                client.log_metric(mlflow_run_id, "accuracy", accuracy, step=epoch)
                client.log_metric(mlflow_run_id, "epoch", epoch, step=epoch)
            except Exception as e:
                print(f"Warning: Failed to log metrics to MLflow: {e}")
        
        # Save checkpoint every 2 epochs or at the end
        checkpoint = None
        if (epoch + 1) % 2 == 0 or epoch == epochs - 1:
            # Create temp directory in /tmp (always exists in containers)
            checkpoint_dir = tempfile.mkdtemp(prefix="checkpoint_")
            model_to_save = model.module if hasattr(model, 'module') else model
            torch.save(
                model_to_save.state_dict(),  # Save unwrapped model
                os.path.join(checkpoint_dir, "model.pt")
            )
            checkpoint = Checkpoint.from_directory(checkpoint_dir)
        
        ray.train.report(metrics, checkpoint=checkpoint)
        
        if is_rank_0:
            print(f"Epoch {epoch}: "
                  f"Train={avg_train_loss:.4f}, "
                  f"Test={avg_test_loss:.4f}, "
                  f"Acc={accuracy:.4f}")


# Main

def main() -> None:
    """Launch distributed training with MLflow tracking"""
    
    print("\n" + "="*70)
    print(" DISTRIBUTED PYTORCH TRAINING WITH RAY + MLFLOW")
    print("="*70 + "\n")
    
    # Connect to Ray cluster first
    ray.init(address=Config.RAY_ADDRESS, ignore_reinit_error=True)
    print(f" Connected to Ray cluster: {Config.RAY_ADDRESS}")
    
    # Detect GPU availability safely using Ray remote function
    # This avoids initializing CUDA in the driver process
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
    
    # Start MLflow run
    with mlflow.start_run(run_name="training") as run:
        run_id = run.info.run_id
        
        # Training configuration
        train_config = {
            "lr": Config.LEARNING_RATE,
            "batch_size": Config.BATCH_SIZE,
            "epochs": Config.EPOCHS,
            "seed": 42,  # For reproducibility
            "mlflow_tracking_uri": Config.MLFLOW_TRACKING_URI,
            "mlflow_run_id": run_id,
            "mlflow_experiment_name": Config.MLFLOW_EXPERIMENT,
        }
        
        # Log parameters to MLflow
        mlflow.log_params(train_config)
        mlflow.log_params({
            "num_workers": Config.NUM_WORKERS,
            "framework": "pytorch",
            "model": "ConvNet",
            "dataset": "MNIST",
            "use_gpu": use_gpu,
        })
        
        # Ray Train configuration with auto-detected GPU
        scaling_config = ScalingConfig(
            num_workers=Config.NUM_WORKERS,
            use_gpu=use_gpu,  # Auto-detected via Ray remote function
            resources_per_worker={
                "CPU": 2,
                "GPU": 1 if use_gpu else 0,
            }
        )
        
        # S3 storage for multi-node cluster (required by Ray Train)
        # NOTE: path must NOT include s3:// prefix when using storage_filesystem
        s3_fs = pafs.S3FileSystem(
            endpoint_override=Config.AWS_S3_ENDPOINT_URL,
            access_key=Config.AWS_ACCESS_KEY_ID,
            secret_key=Config.AWS_SECRET_ACCESS_KEY,
            region=Config.AWS_DEFAULT_REGION
        )
        
        run_config = RunConfig(
            name="mnist_distributed_training",
            storage_path=f"{Config.S3_BUCKET}/ray_results",  # NO s3:// prefix!
            storage_filesystem=s3_fs,
        )
        
        # Create and run trainer
        trainer = TorchTrainer(
            train_func,
            train_loop_config=train_config,
            scaling_config=scaling_config,
            run_config=run_config
        )
        
        print("🏋️ Starting training...\n")
        result = trainer.fit()
        
        # Handle checkpoint
        with result.checkpoint.as_directory() as checkpoint_dir:
            # Copy to permanent location
            local_checkpoint_dir = tempfile.mkdtemp(prefix="mlflow_ckpt_")
            
            for file in Path(checkpoint_dir).rglob("*"):
                if file.is_file():
                    dest = Path(local_checkpoint_dir) / file.relative_to(checkpoint_dir)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, dest)
            
            # Log to MLflow
            mlflow.log_artifacts(local_checkpoint_dir, "model")
            
            # Cleanup
            shutil.rmtree(local_checkpoint_dir)
        
        # Summary
        print("\n" + "="*70)
        print(" TRAINING COMPLETE")
        print("="*70)
        print(f" Final Accuracy: {result.metrics['accuracy']:.2%}")
        print(f" Final Loss: {result.metrics['test_loss']:.4f}")
        print(f" Checkpoint: {result.checkpoint}")
        print(f" MLflow: {Config.MLFLOW_TRACKING_URI}")
        print(f"  S3: s3://{Config.S3_BUCKET}/ray_results/{run_id}")
        print("="*70 + "\n")
        
        ray.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n Training failed: {e}")
        
        # Log failure to MLflow if possible
        try:
            mlflow.log_param("status", "failed")
            mlflow.log_param("error", str(e))
        except Exception:
            pass
        
        traceback.print_exc()
        raise