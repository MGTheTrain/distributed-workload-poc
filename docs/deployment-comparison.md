# Deployment Options: Cloud vs VM vs HPC

**Decision guide for deploying distributed ML workloads.**

> **Note on framing:** These options are common deployment *approaches*, not strictly equivalent technologies. VMs and HPC clusters are *infrastructure*; Kubernetes and Slurm are *orchestration* that runs on top of it (managed Kubernetes like EKS runs on cloud VMs; self-hosted Kubernetes runs on VMs or bare metal). They're listed together because teams evaluate them together when deciding how to deploy ML workloads — but they sit at different layers of the stack.

## Deployment Models

### 1️⃣ Managed Kubernetes (Cloud-Native)

**Providers:** [EKS](https://aws.amazon.com/eks/), [GKE](https://cloud.google.com/kubernetes-engine), [AKS](https://azure.microsoft.com/en-us/products/kubernetes-service)

**Pros:**
- ✅ Auto-scaling (nodes + pods, depending on configuration)
- ✅ Infrastructure-level self-healing (pod restart, rescheduling)
- ✅ Declarative deployment (YAML, operators)
- ✅ Observability ecosystem (Prometheus, Grafana, etc.)
- ✅ Managed control plane

**Cons:**
- ❌ Operational complexity (Kubernetes learning curve)
- ❌ Cost overhead (control plane, networking, load balancers)
- ❌ Network latency overhead vs bare-metal systems

**Best for:** Production ML systems, elastic workloads, multi-tenant environments

### 2️⃣ Self-Hosted Kubernetes

**Tools:** [Rancher](https://www.rancher.com/), [Kubeadm](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/), [Kind](https://kind.sigs.k8s.io/) (dev)

**Pros:**
- ✅ Full infrastructure control
- ✅ Potential cost efficiency at scale
- ✅ Custom networking (e.g., RDMA, InfiniBand where available)

**Cons:**
- ❌ High operational burden (upgrades, security, observability)
- ❌ Requires deep Kubernetes expertise
- ❌ No native node provisioning unless separately integrated

**Best for:** On-prem environments, compliance-constrained deployments, specialized hardware setups

### 3️⃣ Virtual Machines (Terraform / Ansible / Puppet / Chef)

**Providers:** [EC2](https://aws.amazon.com/ec2/), [Compute Engine](https://cloud.google.com/compute), [Azure VMs](https://azure.microsoft.com/en-us/products/virtual-machines)

**Pros:**
- ✅ High flexibility and transparency
- ✅ Full OS-level control (SSH access, custom stacks)
- ✅ Low abstraction overhead

**Cons:**
- ❌ No built-in orchestration or scheduling
- ❌ Manual scaling and failure handling unless custom-built
- ❌ Multi-node coordination must be implemented explicitly

**Best for:** Small-to-medium experiments, debugging, fixed-size workloads, custom systems

### 4️⃣ HPC Clusters (Slurm)

**Systems:** [NERSC](https://www.nersc.gov/), [TACC](https://www.tacc.utexas.edu/), [Summit](https://www.olcf.ornl.gov/summit/)

**Pros:**
- ✅ Very high efficiency for tightly coupled workloads
- ✅ Efficient use of specialized interconnects (e.g., InfiniBand, RoCE; plus intra-node NVLink where available)
- ✅ Mature batch scheduling for large-scale compute jobs

**Cons:**
- ❌ Queue-based allocation (no elasticity during job execution)
- ❌ Limited scheduler-level fault recovery (application-managed checkpointing required)
- ❌ Batch-oriented workflow (not suited for interactive or continuously scaling workloads)

**Best for:** Large-scale distributed training, scientific simulations, tightly coupled HPC workloads

## Decision Matrix

| Factor | Managed K8s | Self-Hosted K8s | VMs | HPC |
|--------|-------------|-----------------|-----|-----|
| Time to initial deployment* | Minutes | Days–weeks | Minutes | Minutes (existing center) to months (build) |
| Scaling | Automatic (config-dependent) | Manual / custom | Manual | Fixed per job |
| Fault Tolerance | Infrastructure-level self-healing | Infrastructure-level (DIY responsibility) | None inherent | Limited scheduler support |
| Infrastructure cost model | Usage-based cloud spending | Capital + operations | Usage-based or owned | Shared institutional or dedicated |
| Complexity | Medium | High | Low | High |
| Operational scalability | High | High | Low (manual) | High (batch) |
| Flexibility | High | High | High | Low |
| Best For | Production ML systems | On-prem / custom infra | Experiments | HPC / pretraining |

\* *Assumes prerequisites exist (cloud account/VPC/IAM for managed offerings, an account on an existing HPC center, etc.). Building the underlying infrastructure from scratch takes substantially longer.*

> **On cost and throughput:** Raw cost and raw throughput are driven mostly by GPU type, utilization, networking, storage, and implementation — not by the deployment model itself. The same 8×H100 hardware delivers comparable throughput whether driven by torchrun on a VM or by a Ray job on Kubernetes; orchestration adds overhead but it's usually small. The matrix therefore compares *cost model* and *operational scalability* rather than a single "cost" or "throughput" score.

## Ray + Managed Kubernetes (Common Pattern)

**Why it is widely used:**
- Elastic scheduling via Kubernetes + Ray autoscaling (configuration-dependent)
- Fault isolation at pod + task level (framework-dependent)
- Strong observability and deployment automation

**Important caveat:**
- Fault tolerance and elasticity depend on both **Ray configuration** and **training framework support**, not Kubernetes alone.

## A Note on Managed ML Platforms

Many teams weighing "VMs vs Kubernetes vs HPC" ultimately choose a fully-managed ML platform instead — e.g. [Amazon SageMaker](https://aws.amazon.com/sagemaker/), [Vertex AI](https://cloud.google.com/vertex-ai), or [Azure Machine Learning](https://azure.microsoft.com/en-us/products/machine-learning). These trade infrastructure control for reduced operational burden and are worth evaluating alongside the self-operated options above, especially for smaller teams.

## Resources
- https://docs.ray.io/en/latest/cluster/kubernetes/index.html
- https://aws.github.io/aws-eks-best-practices/
- https://registry.terraform.io/modules/terraform-aws-modules/eks/aws/latest

## TL;DR

Managed Kubernetes is a common default for scalable ML systems, while HPC is optimized for tightly coupled batch workloads and VMs remain the most flexible low-level option requiring manual orchestration. These sit at different layers of the stack, and raw cost/throughput depend more on hardware and utilization than on the deployment model.
