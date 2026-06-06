# Traditional HPC (Slurm + MPI/torchrun) vs Cloud-Native ML (Kubernetes + Ray)

**Comparison of two common approaches for distributed ML workloads.**

> **Note on framing:** Slurm and Ray are not direct equivalents — they solve different layers of the stack. Slurm is a *resource manager / batch scheduler* (its peer is Kubernetes), while Ray is a *distributed execution runtime* (its peers are MPI, torchrun, and DeepSpeed). This comparison is therefore really *traditional HPC batch scheduling* vs *cloud-native distributed ML orchestration*.
>
> | Layer | Stack A (Traditional HPC) | Stack B (Cloud-Native ML) |
> |-------|---------------------------|---------------------------|
> | Resource manager | Slurm | Kubernetes |
> | Distributed runtime | MPI / torchrun / DeepSpeed | Ray |
> | Infrastructure | HPC cluster | Cloud-native cluster |

The deeper philosophical difference: the traditional HPC model optimizes for allocating a fixed set of resources to a job and maximizing efficiency during execution, whereas cloud-native systems optimize for operating many workloads simultaneously and adapting resource allocation over time.

## Side-by-Side Workflows

### Traditional HPC (Slurm) Workflow

**Scenario:** Large LLM pretraining on a multi-node GPU cluster

```bash
# Step 1: Submit job
$ sbatch train_llm.slurm
# Requests N nodes, M GPUs per node, walltime limit

# Step 2: Queueing & allocation
# Slurm places job in queue
# When resources are available, allocates a set of nodes exclusively
# Topology-aware scheduling (e.g. topology/tree plugin) can place nodes
# on the same switch to minimize interconnect hops

# Step 3: Launch training
$ srun python train.py
# Often launches distributed processes (MPI, NCCL, torchrun, DeepSpeed)
# All allocated nodes are expected to start together

# Step 4: Monitoring
# Slurm provides job status, resource usage, exit codes
# Logs typically written to shared filesystem

# Step 5: Checkpoint & recovery
# Checkpointing is application-managed
# On failure, job is usually resubmitted manually (or via wrappers)
```

**Characteristics:**

* ✅ **Peak efficiency:** Very high for large tightly-coupled jobs (minimal orchestration overhead)
* ❌ **Flexibility:** Low (queue-based scheduling, static allocation per job)
* ❌ **Elasticity:** Generally fixed allocations for a job's lifetime; dynamic resizing exists in some schedulers but is uncommon and not the dominant operating model
* ⚠️ **Fault tolerance:** Limited at scheduler level; depends on application checkpointing
* 🎯 **Best for:** Large tightly-coupled simulations, scientific computing, distributed AI training, and batch-oriented supercomputing workloads

### Cloud-Native ML (Kubernetes + Ray) Workflow

**Scenario:** LLM training, fine-tuning, or distributed experimentation on GPU infrastructure

```python
# Step 1: Provision cluster
# Kubernetes schedules GPU nodes (cloud or on-prem)
# Ray head + worker pods deployed on cluster
# Topology-aware placement requires add-ons (Volcano, Kueue,
# or pod topology spread constraints) to avoid scattering a job across racks

# Step 2: Submit training job
from ray.train.torch import TorchTrainer

trainer = TorchTrainer(...)
result = trainer.fit()

# Step 3: Dynamic execution
# Ray schedules tasks across available workers
# Can run multiple training / tuning jobs concurrently
# Autoscaling may add/remove worker pods

# Step 4: Monitoring
# Ray dashboard (default :8265)
# Kubernetes dashboards + Prometheus/Grafana metrics

# Step 5: Checkpoint & recovery
# Ray can retry failed tasks and actors automatically
# Recovery of distributed training state still depends on framework-level checkpointing
# Elastic training supported in some frameworks
```

**Characteristics:**

* ⚡ **Peak efficiency:** High; may incur additional orchestration overhead vs bare-metal HPC, though the gap is often small relative to networking, storage, data loading, and model implementation
* ✅ **Flexibility:** High (multi-job scheduling, heterogeneous workloads)
* ✅ **Elasticity:** Supported via Kubernetes autoscaling + Ray autoscaler (workload-dependent)
* ⚠️ **Fault tolerance:** Task/actor-level retries + checkpoint-based recovery (framework-dependent); a lost worker in a multi-node training job remains a complex event
* 🎯 **Best for:** Iterative ML development, hyperparameter tuning, mixed workloads, production ML pipelines, and large-scale training on cloud-native infrastructure (e.g., Anyscale, some NVIDIA stacks)

## Feature Comparison

| Feature                   | Traditional HPC (Slurm)                                  | Cloud-Native ML (Kubernetes + Ray)                       |
| ------------------------- | -------------------------------------------------------- | -------------------------------------------------------- |
| Resource allocation model | Static per job (queued allocation)                       | Dynamic (pod-based scheduling + autoscaling)             |
| Job execution model       | Gang-scheduled distributed jobs                          | Task- and actor-oriented execution                       |
| Fault handling            | Application-driven checkpoint/restart                    | Scheduler + framework-level retries                      |
| Scaling during execution  | Generally not supported                                  | Supported (depending on setup)                           |
| Workload type             | Batch workloads, from many small jobs to large tightly-coupled jobs | Many concurrent and heterogeneous jobs        |
| Topology awareness        | Native (optimizes for minimal network switch hops)       | Requires add-ons (Volcano, Kueue, topology constraints)  |
| Data paradigm             | Shared parallel filesystem (Lustre / GPFS)               | Object storage streaming + in-memory (Plasma)            |
| Monitoring                | Slurm accounting + logs                                  | Metrics + dashboards + logs                              |
| Operational model         | Batch scheduling                                         | Continuous orchestration                                 |
| Peak efficiency           | Very high (minimal overhead)                             | High (orchestration overhead present)                    |

## Networking & Storage Assumptions

A distinction that the scheduler/runtime split alone doesn't capture:

* **Traditional HPC** typically assumes low-latency interconnects (InfiniBand / RoCE), RDMA, and tightly-coupled nodes. Slurm is natively topology-aware and schedules jobs to minimize switch hops. Data usually comes from a massive shared parallel filesystem (Lustre, GPFS) mounted directly on the host — fast, but bounded by the storage cluster.
* **Cloud-native systems** prioritize operational flexibility, heterogeneous clusters, and service-oriented architecture. Topology-aware placement is not free — without operators like Volcano, Kueue, or pod topology spread constraints, Kubernetes may scatter a single training job across racks and degrade NCCL performance. Data is often streamed from object storage (S3, GCS) into Ray's distributed shared memory (Plasma store), avoiding the need for an expensive parallel filesystem for many ML workloads.

## The Convergence Era

The boundary between these stacks is blurring in production:

* **Ray on Slurm:** Many teams use Slurm to allocate a static block of GPU nodes, then spin up a transient Ray cluster inside that allocation — combining HPC networking performance with Ray's developer-friendly APIs.
* **Kueue on Kubernetes:** Kubernetes is adopting classic HPC features via projects like Kueue, bringing batch queueing, fair-sharing, and strict resource quotas to cloud-native clusters.

The two models are converging from both directions rather than remaining strictly separate.

## Key Clarifications

* Slurm does not provide automatic recovery of distributed tasks; recovery is application-driven.
* Kubernetes provides container restart semantics, but distributed fault tolerance is provided by frameworks like Ray — and even then, recovery of distributed training state depends on framework-level checkpointing.
* "Elastic training" depends on framework and workload design; it is not guaranteed.
* High-performance interconnects (e.g., InfiniBand) are common in HPC but are not a Slurm requirement.
* Slurm and Ray operate at different layers: Kubernetes is the closer analogue to Slurm, while Ray is closer to MPI/torchrun/DeepSpeed.

## Resources

* [https://docs.ray.io/en/latest/cluster/vms/user-guides/community/slurm.html](https://docs.ray.io/en/latest/cluster/vms/user-guides/community/slurm.html)
* [https://docs.ray.io/en/latest/cluster/kubernetes/index.html](https://docs.ray.io/en/latest/cluster/kubernetes/index.html)
* [https://slurm.schedmd.com/documentation.html](https://slurm.schedmd.com/documentation.html)

## TL;DR

Traditional HPC (Slurm + MPI/torchrun): optimized for **static, high-efficiency batch workloads**.
Cloud-Native ML (Kubernetes + Ray): optimized for **flexible, elastic, multi-workload ML systems**.
The line between them is blurring as each adopts the other's strengths.
