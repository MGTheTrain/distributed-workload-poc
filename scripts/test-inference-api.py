#!/usr/bin/env python3
"""
Download MNIST to ./data, save a few test images,
and invoke the Ray Serve inference endpoints.
"""

import requests
from pathlib import Path
from torchvision import datasets, transforms
from PIL import Image
import numpy as np
from colorama import Fore, init

# Initialize colorama
init(autoreset=True)

# Configuration

BASE_URL = "http://localhost:8000"
DATA_DIR = Path("./data")
IMG_DIR = DATA_DIR / "imgs"

IMG_DIR.mkdir(parents=True, exist_ok=True)

mnist_dir = DATA_DIR / "MNIST"

# Check if MNIST dataset exists, otherwise download
if not mnist_dir.exists():
    print(Fore.GREEN + "Downloading MNIST dataset...")
    mnist = datasets.MNIST(
        root=DATA_DIR,
        train=False,
        download=True,
        transform=transforms.ToTensor(),
    )
else:
    print(Fore.YELLOW + "MNIST dataset already exists, skipping download.")
    mnist = datasets.MNIST(
        root=DATA_DIR,
        train=False,
        download=False,
        transform=transforms.ToTensor(),
    )

# Save a few test images as PNG
image_paths = []

for i in range(3):
    img_tensor, label = mnist[i]
    img_array = (img_tensor.squeeze().numpy() * 255).astype(np.uint8)

    img_path = IMG_DIR / f"digit_{label}.png"
    Image.fromarray(img_array).save(img_path)

    image_paths.append(img_path)

print(Fore.BLUE + "Saved test images:", image_paths)

# Health check
health = requests.get(f"{BASE_URL}/")
print(Fore.BLUE + f"Health:", Fore.WHITE + f"{health.json()}")

# Single prediction
with open(image_paths[0], "rb") as f:
    response = requests.post(
        f"{BASE_URL}/predict",
        files={"file": f},
    )
    print(Fore.BLUE + f"Single prediction:", Fore.WHITE + f"{response.json()}")

# Batch prediction
files = [("files", open(p, "rb")) for p in image_paths]
response = requests.post(
    f"{BASE_URL}/batch_predict",
    files=files,
)
print(Fore.BLUE + f"Batch prediction:", Fore.WHITE + f"{response.json()}")
