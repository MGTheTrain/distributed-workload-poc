#!/bin/bash
#SBATCH --job-name=ray-etl
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:00:00
#SBATCH --partition=compute

# Start Ray cluster on SLURM
HEAD_NODE=$(scontrol show hostname $SLURM_NODELIST | head -n1)
HEAD_IP=$(srun --nodes=1 --ntasks=1 -w $HEAD_NODE hostname --ip-address)

echo "Starting Ray head node on $HEAD_NODE ($HEAD_IP)"

# Start head node
srun --nodes=1 --ntasks=1 -w $HEAD_NODE \
    ray start --head --port=6379 --dashboard-host=0.0.0.0 --block &

sleep 10

# Start worker nodes
WORKER_NODES=$(scontrol show hostname $SLURM_NODELIST | tail -n +2)
for node in $WORKER_NODES; do
    echo "Starting Ray worker on $node"
    srun --nodes=1 --ntasks=1 -w $node \
        ray start --address=$HEAD_IP:6379 --block &
done

sleep 5

# Run workload
echo "Running ETL workload..."
python /workspace/workloads/etl/ray_etl_pipeline.py

# Cleanup
ray stop
