# Backlog

### Ray on HPC Clusters (SLURM)
- **Use case:** Maximum throughput for large-scale LLM pretraining
- **Pattern:** Ray's [`symmetric-run`](https://docs.ray.io/en/latest/cluster/vms/user-guides/community/slurm.html) command on SLURM
- **Network:** InfiniBand for multi-node GPU training
- **Reference:** See [`scripts/ray_on_slurm.sh`](./scripts/ray_on_slurm.sh) (example only)

### Ray on Virtual Machines
- **Use case:** Fixed-size workloads, maximum flexibility
- **Pattern:** [Ray on VMs](https://docs.ray.io/en/latest/cluster/vms/index.html) with Terraform/Ansible/Puppet/Chef
- **Tradeoff:** Manual scaling vs K8s auto-scaling

Also checkout:
- [HPC vs Kubernetes Workflows](./docs/hpc-vs-kubernetes.md)
- [Deployment Comparison](./docs/deployment-comparison.md)
