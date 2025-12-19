#!/usr/bin/env python3
"""
Distributed ML Model Serving with Ray Serve and MLflow
Handles model loading from MLflow with S3 backend, autoscaling, batch inference and FastAPI integration
"""
import io
import os
import tempfile
from pathlib import Path
from typing import List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms
from PIL import Image

from fastapi import FastAPI, File, UploadFile, HTTPException
import mlflow
from ray import serve


# Configuration

class Config:
    DATA_DIR = Path(os.getenv("DATA_DIR", "/workspace/data"))
    MODEL_DIR = Path(os.getenv("MODEL_DIR", str(DATA_DIR / "models")))
    MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    MLFLOW_EXPERIMENT = "ray-train-pytorch"
    RAY_ADDRESS = os.getenv("RAY_ADDRESS", "ray://localhost:6379")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "test")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
    AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "http://localstack:4566")
    S3_BUCKET = os.getenv("S3_BUCKET", "mlflow-artifacts")
    MIN_REPLICAS = int(os.getenv("MIN_REPLICAS", "1"))
    MAX_REPLICAS = int(os.getenv("MAX_REPLICAS", "4"))
    TARGET_REQUESTS_PER_REPLICA = int(os.getenv("TARGET_REQUESTS_PER_REPLICA", "10"))
    RUN_ID = os.getenv("MLFLOW_RUN_ID", None)

# Environment setup for MLflow S3 access
os.environ.update({
    "AWS_ACCESS_KEY_ID": Config.AWS_ACCESS_KEY_ID,
    "AWS_SECRET_ACCESS_KEY": Config.AWS_SECRET_ACCESS_KEY,
    "AWS_DEFAULT_REGION": Config.AWS_DEFAULT_REGION,
    "MLFLOW_S3_ENDPOINT_URL": Config.AWS_S3_ENDPOINT_URL,
})
mlflow.set_tracking_uri(Config.MLFLOW_TRACKING_URI)

# Model

class ConvNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(1, 32, 3)
        self.conv2 = nn.Conv2d(32, 64, 3)
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


# Model Loading Utilities

def load_model_from_mlflow(run_id: str, artifact_path: str = "model") -> Path:
    local_path = tempfile.mkdtemp(prefix="mlflow_model_")
    artifact_uri = f"runs:/{run_id}/{artifact_path}"
    mlflow.artifacts.download_artifacts(artifact_uri=artifact_uri, dst_path=local_path)
    model_files = list(Path(local_path).rglob("*.pt"))
    if not model_files:
        raise FileNotFoundError(f"No .pt model file found in {local_path}")
    return model_files[0]

def get_best_model_from_mlflow(experiment_name: str) -> Path:
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if not experiment:
        raise ValueError(f"Experiment '{experiment_name}' not found")
    runs = mlflow.search_runs(experiment_ids=[experiment.experiment_id], order_by=["metrics.accuracy DESC"], max_results=1)
    if runs.empty:
        raise ValueError(f"No runs found in experiment '{experiment_name}'")
    best_run = runs.iloc[0]
    return load_model_from_mlflow(best_run["run_id"])


# FastAPI App

app = FastAPI(title="MNIST Inference API", version="1.0.0")

@serve.deployment(
    autoscaling_config={
        "min_replicas": Config.MIN_REPLICAS,
        "max_replicas": Config.MAX_REPLICAS,
        "target_num_ongoing_requests_per_replica": Config.TARGET_REQUESTS_PER_REPLICA
    },
    ray_actor_options={"num_cpus": 1}
)
@serve.ingress(app)
class MNISTInferenceAPI:
    def __init__(self, model_source: str = "mlflow", model_identifier: Optional[str] = None):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_source = model_source
        self.model_identifier = model_identifier
        model_path = self._load_model()
        self.model = ConvNet()
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.to(self.device)
        self.model.eval()
        self.transform = transforms.Compose([
            transforms.Grayscale(1),
            transforms.Resize((28,28)),
            transforms.ToTensor(),
            transforms.Normalize((0.1307,), (0.3081,))
        ])
        self.request_count = 0

    def _load_model(self) -> Path:
        if self.model_source == "mlflow":
            return load_model_from_mlflow(self.model_identifier) if self.model_identifier else get_best_model_from_mlflow(Config.MLFLOW_EXPERIMENT)
        elif self.model_source == "local":
            path = Path(self.model_identifier) if self.model_identifier else Config.MODEL_DIR / "model.pt"
            if not path.exists():
                raise FileNotFoundError(f"Model not found at {path}")
            return path
        else:
            raise ValueError(f"Unknown model source: {self.model_source}")

    @app.get("/")
    async def root(self):
        return {"status":"healthy","model_source":self.model_source,"requests_served":self.request_count}

    @app.post("/predict")
    async def predict(self, file: UploadFile = File(...)):
        self.request_count += 1
        try:
            contents = await file.read()
            img = Image.open(io.BytesIO(contents))
            tensor = self.transform(img).unsqueeze(0).to(self.device)
            with torch.no_grad():
                output = self.model(tensor)
                prob = F.softmax(output, dim=1)
                pred = output.argmax(dim=1).item()
            return {"predicted_digit": pred, "confidence": float(prob[0][pred]), "filename": file.filename}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/batch_predict")
    async def batch_predict(self, files: List[UploadFile] = File(...)):
        self.request_count += len(files)
        results = []
        for file in files:
            contents = await file.read()
            img = Image.open(io.BytesIO(contents))
            tensor = self.transform(img).unsqueeze(0).to(self.device)
            with torch.no_grad():
                output = self.model(tensor)
                prob = F.softmax(output, dim=1)
                pred = output.argmax(dim=1).item()
            results.append({"filename": file.filename, "predicted_digit": pred, "confidence": float(prob[0][pred])})
        return {"predictions": results}

    @app.get("/stats")
    async def stats(self):
        return {"requests_served": self.request_count, "model_source": self.model_source, "device": str(self.device)}


# Deployment binding for serve deploy

if Config.RUN_ID:
    deployment = MNISTInferenceAPI.bind(model_source="mlflow", model_identifier=Config.RUN_ID)
else:
    deployment = MNISTInferenceAPI.bind(model_source="mlflow", model_identifier=None)
