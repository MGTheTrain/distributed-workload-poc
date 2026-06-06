#!/usr/bin/env python3
"""
End-to-end test for the Ray Serve inference endpoints.

Downloads a few MNIST test images, waits for Ray Serve to become ready,
then exercises the health, single-prediction, and batch-prediction routes.

Run with:  pytest scripts/test_inference_api.py
The Serve base URL can be overridden with the BASE_URL env var.
"""

import os
import time
from pathlib import Path

import numpy as np
import pytest
import requests
from PIL import Image
from torchvision import datasets, transforms

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
IMG_DIR = DATA_DIR / "imgs"
NUM_IMAGES = 3


def _wait_for_serve(base_url: str, attempts: int = 30, delay: int = 2) -> None:
    """Block until Ray Serve answers GET / with a non-empty 200, or fail."""
    last_err: Exception | None = None
    for _ in range(attempts):
        try:
            resp = requests.get(f"{base_url}/", timeout=3)
            if resp.status_code == 200 and resp.text.strip():
                return
        except requests.exceptions.RequestException as exc:
            last_err = exc
        time.sleep(delay)
    pytest.fail(
        f"Ray Serve not ready at {base_url} after {attempts * delay}s "
        f"(last error: {last_err})"
    )


@pytest.fixture(scope="session")
def image_paths() -> list[Path]:
    """Save a few MNIST test digits to disk and return their paths."""
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    download = not (DATA_DIR / "MNIST").exists()
    mnist = datasets.MNIST(
        root=str(DATA_DIR),
        train=False,
        download=download,
        transform=transforms.ToTensor(),
    )

    paths = []
    for i in range(NUM_IMAGES):
        img_tensor, label = mnist[i]
        img_array = (img_tensor.squeeze().numpy() * 255).astype(np.uint8)
        path = IMG_DIR / f"digit_{label}.png"
        Image.fromarray(img_array).save(path)
        paths.append(path)
    return paths


@pytest.fixture(scope="session", autouse=True)
def serve_ready() -> None:
    """Ensure Ray Serve is up before any test hits an endpoint."""
    _wait_for_serve(BASE_URL)


def test_health() -> None:
    resp = requests.get(f"{BASE_URL}/", timeout=10)
    assert resp.status_code == 200, resp.text
    assert resp.json()  # non-empty body


def test_single_prediction(image_paths: list[Path]) -> None:
    with open(image_paths[0], "rb") as f:
        resp = requests.post(f"{BASE_URL}/predict", files={"file": f}, timeout=30)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "prediction" in body or body, body


def test_batch_prediction(image_paths: list[Path]) -> None:
    opened = [open(p, "rb") for p in image_paths]
    try:
        files = [("files", f) for f in opened]
        resp = requests.post(f"{BASE_URL}/batch_predict", files=files, timeout=30)
    finally:
        for f in opened:
            f.close()
    assert resp.status_code == 200, resp.text
    assert resp.json(), resp.text
