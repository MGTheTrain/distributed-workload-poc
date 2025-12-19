#!/usr/bin/env python3
import argparse
import os
import boto3

# Environment configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "test")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "http://localhost:4566")

# Parse input arguments
parser = argparse.ArgumentParser(description="Download file from LocalStack S3")
parser.add_argument("--bucket", required=True, help="S3 bucket name")
parser.add_argument("--key", required=True, help="S3 object key (path in bucket)")
parser.add_argument("--output", default="model.pt", help="Local filename to save the object")
args = parser.parse_args()

# S3 client pointing to LocalStack
s3 = boto3.client(
    "s3",
    endpoint_url=AWS_S3_ENDPOINT_URL,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_DEFAULT_REGION,
)

# Download file
s3.download_file(args.bucket, args.key, args.output)
print(f"✅ File downloaded to {args.output} from s3://{args.bucket}/{args.key}")

# e.g. 
# python scripts/download-s3-artifact.py \
#     --bucket mlflow-artifacts \
#     --key 1/02daa299ed5f4894b894ea9a015ea511/artifacts/model/model.pt \
#     --output model.pt