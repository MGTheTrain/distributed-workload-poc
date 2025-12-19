#!/usr/bin/env python3
"""
Ray Data ETL Pipeline with Integrated Data Generation and S3 Storage
Processes sales data using Ray Data API and persists to S3
"""
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
import traceback

import ray
from ray.data.aggregate import Sum, Mean, Count
import pandas as pd
import numpy as np
import boto3
from botocore.exceptions import ClientError


# Configuration

class Config:
    """ETL pipeline configuration"""
    # Paths
    DATA_DIR = Path(os.getenv("DATA_DIR", "/workspace/data"))
    INPUT_FILE = Path(os.getenv("INPUT_FILE", str(DATA_DIR / "sales_data.csv")))
    OUTPUT_FILE = Path(os.getenv("OUTPUT_FILE", str(DATA_DIR / "processed_sales_ray_data.parquet")))
    
    # Ray
    RAY_ADDRESS = os.getenv("RAY_ADDRESS", "ray://localhost:10001")
    
    # S3 / LocalStack
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "test")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
    AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "http://localstack:4566")
    S3_BUCKET = os.getenv("S3_BUCKET", "mlflow-artifacts")
    S3_PREFIX = os.getenv("S3_PREFIX", "etl-results")
    
    # Data generation settings
    NUM_ROWS = int(os.getenv("NUM_ROWS", "200000"))
    RANDOM_SEED = 42


# Configure S3 environment
os.environ.update({
    "AWS_ACCESS_KEY_ID": Config.AWS_ACCESS_KEY_ID,
    "AWS_SECRET_ACCESS_KEY": Config.AWS_SECRET_ACCESS_KEY,
    "AWS_DEFAULT_REGION": Config.AWS_DEFAULT_REGION,
})


# S3 Utilities

def get_s3_client():
    """Create configured S3 client for LocalStack/AWS"""
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
        print(f" S3 bucket exists: {bucket}")
    except ClientError:
        try:
            s3_client.create_bucket(Bucket=bucket)
            print(f" Created S3 bucket: {bucket}")
        except ClientError as e:
            print(f"  Could not create bucket: {e}")
            raise


def upload_to_s3(
    s3_client, 
    local_file: Path, 
    bucket: str, 
    s3_key: str
) -> str:
    """Upload file to S3 and return S3 URI"""
    try:
        file_size_mb = local_file.stat().st_size / 1024 / 1024
        
        print(f" Uploading to S3...")
        print(f"   Local: {local_file}")
        print(f"   Size: {file_size_mb:.2f} MB")
        
        upload_start = time.time()
        s3_client.upload_file(str(local_file), bucket, s3_key)
        upload_time = time.time() - upload_start
        
        s3_uri = f"s3://{bucket}/{s3_key}"
        print(f" Uploaded to: {s3_uri}")
        print(f"   Upload time: {upload_time:.2f}s")
        print(f"   Throughput: {file_size_mb / upload_time:.2f} MB/s")
        
        return s3_uri
        
    except ClientError as e:
        print(f" S3 upload failed: {e}")
        raise


# Data Generation

def generate_sales_data(num_rows: int, output_file: Path) -> None:
    """Generate synthetic sales data for ETL testing"""
    
    print(f"\n Generating {num_rows:,} rows of sales data...")
    
    np.random.seed(Config.RANDOM_SEED)
    
    categories = ['Electronics', 'Clothing', 'Food', 'Books', 'Toys', 'Sports', 'Home', 'Beauty']
    
    # Generate dates over 3-year period
    start_date = datetime.now() - timedelta(days=3*365)
    dates = [start_date + timedelta(days=np.random.randint(0, 3*365)) for _ in range(num_rows)]
    
    # Generate sales data
    data = {
        'product_id': [f'PROD_{i:06d}' for i in np.random.randint(1000, 9999, num_rows)],
        'category': np.random.choice(categories, num_rows),
        'quantity': np.random.randint(1, 100, num_rows),
        'price': np.round(np.random.uniform(5.0, 500.0, num_rows), 2),
        'date': [d.strftime('%Y-%m-%d') for d in dates]
    }
    
    df = pd.DataFrame(data)
    
    # Add data quality issues for testing
    # 5% missing values
    mask = np.random.random(num_rows) < 0.05
    df.loc[mask, 'quantity'] = np.nan
    
    # 2% negative prices (data quality issues)
    mask = np.random.random(num_rows) < 0.02
    df.loc[mask, 'price'] = -df.loc[mask, 'price']
    
    # Save to CSV
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False)
    
    # Summary
    file_size_mb = output_file.stat().st_size / 1024 / 1024
    print(f" Generated {len(df):,} rows")
    print(f" Saved to: {output_file}")
    print(f" File size: {file_size_mb:.2f} MB")
    print(f"\n Data summary:")
    print(f"   Categories: {df['category'].nunique()}")
    print(f"   Date range: {df['date'].min()} to {df['date'].max()}")
    print(f"   Price range: ${df['price'].min():.2f} to ${df['price'].max():.2f}")
    print(f"   Missing values: {df.isnull().sum().sum()}")
    print(f"   Data quality issues: {(df['price'] < 0).sum()} negative prices")


# ETL Transformation

def process_row(row: dict) -> list:
    """
    Transform a single sales row with data quality checks
    
    Filters out:
    - Rows with missing quantity or price
    - Rows with invalid revenue (<=0)
    - Rows with invalid dates
    
    Returns:
        List containing transformed row dict, or empty list if invalid
    """
    # Data quality checks
    if pd.isna(row.get('quantity')) or pd.isna(row.get('price')):
        return []  # Skip rows with missing values
    
    total_revenue = row['quantity'] * row['price']
    if total_revenue <= 0:
        return []  # Skip invalid revenue
    
    # Parse date and extract time dimensions
    try:
        date = pd.to_datetime(row['date'])
        year = date.year
        month = date.month
        quarter = (date.month - 1) // 3 + 1
    except:
        return []  # Skip invalid dates
    
    return [{
        'category': row['category'],
        'year': year,
        'month': month,
        'quarter': quarter,
        'total_revenue': total_revenue,
        'quantity': row['quantity']
    }]


# Main Pipeline

def run_etl_pipeline() -> None:
    """Execute distributed ETL pipeline using Ray Data"""
    
    print("\n" + "="*70)
    print(" RAY DATA ETL PIPELINE WITH S3 STORAGE")
    print("="*70 + "\n")
    
    start_time = time.time()
    
    # Initialize S3 client
    s3_client = get_s3_client()
    ensure_bucket_exists(s3_client, Config.S3_BUCKET)
    
    # Step 0: Generate sample data if not exists
    if not Config.INPUT_FILE.exists():
        print(" Input file not found. Generating sample data...")
        generate_sales_data(Config.NUM_ROWS, Config.INPUT_FILE)
    else:
        print(f" Using existing input file: {Config.INPUT_FILE}")
    
    # Connect to Ray
    ray.init(address=Config.RAY_ADDRESS, ignore_reinit_error=True)
    
    cluster_resources = ray.cluster_resources()
    num_cpus = int(cluster_resources.get('CPU', 0))
    num_nodes = len(ray.nodes())
    
    print(f"\n Connected to Ray cluster:")
    print(f"   Address: {Config.RAY_ADDRESS}")
    print(f"   CPUs: {num_cpus}")
    print(f"   Nodes: {num_nodes}")
    print(f"   GPUs: {int(cluster_resources.get('GPU', 0))}")
    
    try:
        # Step 1: Load data with Ray Data
        print(f"\n📥 Step 1: Loading data from {Config.INPUT_FILE.name}...")
        load_start = time.time()
        
        ds = ray.data.read_csv(str(Config.INPUT_FILE))
        row_count = ds.count()
        
        load_time = time.time() - load_start
        print(f" Loaded {row_count:,} rows in {load_time:.2f}s")
        
        # Step 2: Transform with data quality filtering
        print(f"\n Step 2: Applying transformations and quality filters...")
        transform_start = time.time()
        
        ds_transformed = ds.flat_map(process_row)
        
        transform_time = time.time() - transform_start
        print(f" Transformations applied in {transform_time:.2f}s")
        
        # Step 3: Aggregate by category, year, quarter
        print(f"\n Step 3: Computing aggregations...")
        agg_start = time.time()
        
        agg_ds = ds_transformed.groupby(['category', 'year', 'quarter']).aggregate(
            Sum('total_revenue'),
            Mean('total_revenue'),
            Count(),
            Sum('quantity')
        )
        
        agg_time = time.time() - agg_start
        print(f" Aggregations computed in {agg_time:.2f}s")
        
        # Step 4: Materialize results
        print(f"\n⚡ Step 4: Materializing results...")
        materialize_start = time.time()
        
        result_df = agg_ds.to_pandas()
        
        # Rename columns for clarity
        result_df.columns = [
            'category', 'year', 'quarter',
            'total_revenue_sum', 'total_revenue_mean',
            'record_count', 'quantity_sum'
        ]
        
        # Sort for consistent output
        result_df = result_df.sort_values(['year', 'quarter', 'category'])
        
        materialize_time = time.time() - materialize_start
        output_rows = len(result_df)
        print(f" Materialized {output_rows:,} aggregated rows in {materialize_time:.2f}s")
        
        # Step 5: Save to Parquet locally
        print(f"\n Step 5: Saving results to Parquet...")
        save_start = time.time()
        
        Config.OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        result_df.to_parquet(Config.OUTPUT_FILE, index=False)
        
        output_size_mb = Config.OUTPUT_FILE.stat().st_size / 1024 / 1024
        save_time = time.time() - save_start
        print(f" Results saved locally: {Config.OUTPUT_FILE}")
        print(f" Output size: {output_size_mb:.2f} MB")
        
        # Step 6: Upload to S3
        print(f"\n☁️  Step 6: Uploading to S3...")
        
        # Generate timestamped S3 key for versioning
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        s3_key = f"{Config.S3_PREFIX}/processed_sales_{timestamp}.parquet"
        
        s3_uri = upload_to_s3(
            s3_client,
            Config.OUTPUT_FILE,
            Config.S3_BUCKET,
            s3_key
        )
        
        # Also upload a "latest" version for easy access
        latest_s3_key = f"{Config.S3_PREFIX}/processed_sales_latest.parquet"
        upload_to_s3(
            s3_client,
            Config.OUTPUT_FILE,
            Config.S3_BUCKET,
            latest_s3_key
        )
        
        # Calculate metrics
        elapsed_time = time.time() - start_time
        throughput = row_count / elapsed_time
        records_filtered = row_count - sum(result_df['record_count'])
        filter_rate = (records_filtered / row_count) * 100
        
        # Summary
        print("\n" + "="*70)
        print(" PIPELINE COMPLETED SUCCESSFULLY")
        print("="*70)
        print(f"\n Performance Metrics:")
        print(f"   Total execution time: {elapsed_time:.2f}s")
        print(f"   Throughput: {throughput:,.0f} rows/sec")
        print(f"   Load time: {load_time:.2f}s")
        print(f"   Transform time: {transform_time:.2f}s")
        print(f"   Aggregate time: {agg_time:.2f}s")
        print(f"   Materialize time: {materialize_time:.2f}s")
        print(f"   Save time: {save_time:.2f}s")
        
        print(f"\n Data Metrics:")
        print(f"   Input rows: {row_count:,}")
        print(f"   Output rows: {output_rows:,}")
        print(f"   Records filtered: {records_filtered:,} ({filter_rate:.1f}%)")
        print(f"   Compression ratio: {row_count / output_rows:.1f}x")
        
        print(f"\n Cluster Info:")
        print(f"   Ray address: {Config.RAY_ADDRESS}")
        print(f"   CPUs: {num_cpus}")
        print(f"   Nodes: {num_nodes}")
        
        print(f"\n Storage:")
        print(f"   Local: {Config.OUTPUT_FILE}")
        print(f"   S3 (versioned): {s3_uri}")
        print(f"   S3 (latest): s3://{Config.S3_BUCKET}/{latest_s3_key}")
        
        print("\n Sample Results (Top 10):")
        print(result_df.head(10).to_string(index=False))
        
        print("\n" + "="*70 + "\n")
        
    except Exception as e:
        print(f"\n Pipeline failed: {e}")
        traceback.print_exc()
        raise
    
    finally:
        ray.shutdown()
        print(" Ray cluster disconnected\n")


# Entry Point

def main():
    """Main entry point with error handling"""
    try:
        run_etl_pipeline()
        sys.exit(0)
    except Exception as e:
        print(f"\n ETL Pipeline Error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()