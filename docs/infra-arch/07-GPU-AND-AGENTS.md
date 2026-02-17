# GPU Nodes and Agent Isolation — Future Capabilities

## When Do You Need GPUs in Kubernetes?

GPUs are expensive, specialized hardware. Understanding when you actually need them is critical for cost control.

### GPU-Required Workloads

**Local ML Model Inference:**
- Running LLMs locally (LLaMA, Mistral, medical-specific models)
- Generating embeddings for semantic search
- Image classification or medical imaging analysis
- Real-time inference with <100ms latency requirements

**Model Training and Fine-Tuning:**
- Fine-tuning foundation models on your medical data
- Training custom medical entity recognition models
- Hyperparameter search across multiple model variants

**Batch Processing with GPU Acceleration:**
- Batch embedding generation for 10,000+ medical documents
- Parallel inference jobs that benefit from CUDA parallelism
- Data preprocessing pipelines with GPU-optimized libraries

### GPU NOT Required

**External API Calls:**
- Claude API, OpenAI API, or any hosted LLM service
- These services run on provider infrastructure
- Your cluster only needs CPU for HTTP requests

**Traditional Backend Services:**
- Web servers, REST APIs, GraphQL endpoints
- Databases, Redis, message queues
- CRUD operations and business logic

**AI Doctor Assistant Current State:**
- All AI features use Claude Agent SDK calling external Claude API
- No local models, no embedding generation
- Zero GPU nodes required today

**AI Doctor Future Vision:**
- V2: Add agent tools (deterministic logic, still no GPUs)
- V3: Local embeddings for semantic search (T4 GPUs)
- V4: Fine-tuned medical briefing model (L4 or A100)

## GPU Node Pools in GKE

### Why GKE Standard (Not Autopilot) for GPUs

**Autopilot GPU Support:**
- Added in 2023, but still limited compared to Standard
- Cannot customize GPU driver versions
- Less control over node pool configuration
- Harder to implement cost optimizations like spot instances

**Standard Cluster Advantages:**
- Full control over GPU node pools
- Custom machine types and GPU counts
- Spot instance support (60-91% cheaper)
- Fine-grained autoscaling configuration
- Ability to run multiple GPU node pools with different accelerators

For production GPU workloads, Standard mode is recommended.

### Creating a GPU Node Pool

Start with a T4 GPU node pool (cheapest option for inference):

```bash
# Create GPU node pool in existing cluster
gcloud container node-pools create gpu-pool \
  --cluster=doctor-cluster \
  --zone=us-central1-a \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=0 \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=2 \
  --spot \
  --disk-size=50 \
  --disk-type=pd-standard
```

**Key Parameters Explained:**

- `--machine-type=n1-standard-4`: 4 vCPUs, 15GB RAM (T4 requires ≥4 vCPUs)
- `--accelerator=type=nvidia-tesla-t4,count=1`: One T4 GPU per node
- `--num-nodes=0`: Start with zero nodes (scale up on demand)
- `--min-nodes=0`: Allow scaling to zero when idle
- `--max-nodes=2`: Cap at 2 nodes for cost control
- `--spot`: Use spot instances (70-90% cheaper, can be preempted)

### GPU Options and Pricing

Approximate pricing as of 2026 (varies by region, check GCP pricing):

| GPU | VRAM | On-Demand $/hr | Spot $/hr | Use Case |
|-----|------|----------------|-----------|----------|
| T4 | 16GB | ~$0.35 | ~$0.11 | Inference, embeddings, small models |
| L4 | 24GB | ~$0.70 | ~$0.22 | Faster inference, small fine-tuning |
| A100 40GB | 40GB | ~$2.93 | ~$0.88 | Training, large model fine-tuning |
| A100 80GB | 80GB | ~$3.67 | ~$1.10 | Large model training, big batches |
| H100 | 80GB | ~$8.80 | ~$2.64 | Cutting-edge training, frontier models |

**Cost Savings with Spot Instances:**
- T4 spot: $0.11/hr × 730 hrs/month = ~$80/month per node
- T4 on-demand: $0.35/hr × 730 hrs/month = ~$255/month per node
- Savings: ~$175/month per node (69% reduction)

**Trade-offs:**
- Spot instances can be preempted with 30s notice
- Fine for batch jobs that can retry
- Risky for real-time serving (use on-demand for user-facing inference)
- AI Doctor use case: Spot is fine for batch embeddings, on-demand for real-time briefings

### GPU Driver Installation

GKE automatically installs NVIDIA GPU drivers when you create a GPU node pool:

```bash
# Verify GPU driver installation (run on GPU node)
kubectl debug node/gke-doctor-cluster-gpu-pool-abc123 -it --image=nvidia/cuda:12.0.0-base-ubuntu22.04

# Inside debug pod
nvidia-smi
```

Expected output:
```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 525.85.12    Driver Version: 525.85.12    CUDA Version: 12.0     |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  Tesla T4            Off  | 00000000:00:04.0 Off |                    0 |
| N/A   34C    P0    26W /  70W |      0MiB / 15360MiB |      0%      Default |
+-------------------------------+----------------------+----------------------+
```

### Requesting GPUs in Pod Specs

To schedule a pod on a GPU node, request the `nvidia.com/gpu` resource:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: embedding-generator
  namespace: doctor-app
spec:
  containers:
  - name: embedder
    image: us-central1-docker.pkg.dev/PROJECT/doctor-app/embeddings:v1
    resources:
      limits:
        nvidia.com/gpu: 1  # Request 1 GPU
        memory: "8Gi"
        cpu: "4"
      requests:
        nvidia.com/gpu: 1  # Must equal limits (no fractional GPUs)
        memory: "8Gi"
        cpu: "4"
    env:
    - name: CUDA_VISIBLE_DEVICES
      value: "0"  # Use first GPU
```

**Important Rules:**
- GPU requests MUST equal GPU limits (no fractional GPUs in standard K8s)
- Pods requesting GPUs will ONLY schedule on GPU nodes
- GPU nodes typically have taints to prevent non-GPU pods from scheduling

### Taints and Tolerations for GPU Nodes

GPU nodes often have taints to ensure only GPU workloads run on them:

```bash
# Add taint to GPU node pool (done automatically by GKE)
kubectl taint nodes -l cloud.google.com/gke-nodepool=gpu-pool \
  nvidia.com/gpu=present:NoSchedule
```

GPU pods need tolerations:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-workload
spec:
  tolerations:
  - key: nvidia.com/gpu
    operator: Equal
    value: present
    effect: NoSchedule
  nodeSelector:
    cloud.google.com/gke-accelerator: nvidia-tesla-t4
  containers:
  - name: app
    image: my-gpu-app:v1
    resources:
      limits:
        nvidia.com/gpu: 1
```

### Scaling GPU Nodes to Zero

Minimize costs by scaling GPU nodes to zero when not in use:

```bash
# Create GPU node pool with autoscaling to zero
gcloud container node-pools create gpu-pool \
  --cluster=doctor-cluster \
  --zone=us-central1-a \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=0 \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=3
```

**How It Works:**
1. No GPU pods scheduled → autoscaler scales node pool to 0 nodes (no cost)
2. GPU pod created → autoscaler detects unschedulable pod
3. Autoscaler provisions a GPU node (~2-5 minutes)
4. Pod schedules and runs
5. Pod completes → node becomes idle
6. After 10 minutes idle, autoscaler deletes node

**Cost Impact:**
- Running 24/7: $255/month (on-demand) or $80/month (spot)
- Running 8 hours/day: $85/month (on-demand) or $27/month (spot)
- Running 1 hour/day: $11/month (on-demand) or $3/month (spot)

## Running Agents in Isolated Pods

### Why Isolate Agent Tool Execution?

In AI Doctor V2+, the Claude Agent SDK will dispatch tools that:
- Execute code (lab threshold calculations, drug interaction checks)
- Query external medical databases
- Parse and validate medical documents
- Run custom logic written by medical domain experts

Each tool execution should be isolated for:

**Security:**
- Prevent one tool from accessing another tool's data
- Prevent malicious or buggy tools from accessing patient records
- Limit network access to only required services

**Resource Limits:**
- Prevent runaway tools from consuming all CPU/memory
- Set per-tool CPU and memory quotas
- Timeout long-running tools automatically

**Fault Isolation:**
- A crashing tool doesn't take down the main backend
- Failed tools can retry without affecting other tools
- Each tool gets a clean, reproducible environment

**Auditability:**
- Each tool execution is a separate K8s Job with logs
- Easy to trace which tool ran when and what it did
- Compliance with medical record access requirements

### Kubernetes Primitives for Agent Isolation

#### Jobs for One-Shot Tool Execution

K8s Jobs are perfect for running agent tools:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: lab-check-patient-123
  namespace: doctor-tools
  labels:
    tool: lab-checker
    patient-id: "123"
    briefing-id: "456"
spec:
  ttlSecondsAfterFinished: 300  # Delete job after 5 minutes
  activeDeadlineSeconds: 60     # Timeout after 60 seconds
  backoffLimit: 2               # Retry up to 2 times on failure
  template:
    metadata:
      labels:
        tool: lab-checker
    spec:
      restartPolicy: Never
      serviceAccountName: tool-executor
      containers:
      - name: lab-checker
        image: us-central1-docker.pkg.dev/PROJECT/doctor-app/tools:v1
        command: ["python", "check_labs.py"]
        args: ["--patient-id=123", "--thresholds=strict"]
        resources:
          limits:
            cpu: "500m"
            memory: "256Mi"
          requests:
            cpu: "250m"
            memory: "128Mi"
        securityContext:
          runAsNonRoot: true
          runAsUser: 1000
          readOnlyRootFilesystem: true
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["ALL"]
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
        volumeMounts:
        - name: tmp
          mountPath: /tmp
      volumes:
      - name: tmp
        emptyDir: {}
```

**Backend Dispatch Logic (Python):**

```python
from kubernetes import client, config

async def dispatch_tool(tool_name: str, patient_id: str, params: dict) -> dict:
    """Dispatch agent tool as K8s Job and wait for result."""
    config.load_incluster_config()  # Load K8s config from service account
    batch_v1 = client.BatchV1Api()

    job_name = f"{tool_name}-{patient_id}-{uuid.uuid4().hex[:8]}"

    job = client.V1Job(
        metadata=client.V1ObjectMeta(name=job_name, namespace="doctor-tools"),
        spec=client.V1JobSpec(
            ttl_seconds_after_finished=300,
            active_deadline_seconds=60,
            backoff_limit=2,
            template=client.V1PodTemplateSpec(
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        client.V1Container(
                            name=tool_name,
                            image=f"us-central1-docker.pkg.dev/PROJECT/tools:{tool_name}",
                            command=["python", f"{tool_name}.py"],
                            args=[f"--patient-id={patient_id}", f"--params={json.dumps(params)}"],
                            resources=client.V1ResourceRequirements(
                                limits={"cpu": "500m", "memory": "256Mi"},
                                requests={"cpu": "250m", "memory": "128Mi"},
                            ),
                        )
                    ],
                )
            ),
        )
    )

    # Create job
    batch_v1.create_namespaced_job(namespace="doctor-tools", body=job)

    # Wait for completion (up to 60 seconds)
    await wait_for_job_completion(job_name, namespace="doctor-tools", timeout=60)

    # Read logs for result
    core_v1 = client.CoreV1Api()
    pods = core_v1.list_namespaced_pod(
        namespace="doctor-tools",
        label_selector=f"job-name={job_name}",
    )

    if not pods.items:
        raise Exception(f"No pod found for job {job_name}")

    logs = core_v1.read_namespaced_pod_log(
        name=pods.items[0].metadata.name,
        namespace="doctor-tools",
    )

    # Parse tool output (JSON on last line)
    return json.loads(logs.strip().split("\n")[-1])
```

#### Resource Quotas

Limit total resources consumed by tool pods in the namespace:

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: tool-quota
  namespace: doctor-tools
spec:
  hard:
    requests.cpu: "4"           # Total CPU requests across all tool pods
    requests.memory: "4Gi"      # Total memory requests
    limits.cpu: "8"             # Total CPU limits
    limits.memory: "8Gi"        # Total memory limits
    count/jobs.batch: "10"      # Max 10 concurrent tool jobs
    count/pods: "20"            # Max 20 pods (including completed)
```

**Why This Matters:**
- Prevents a burst of tool executions from overwhelming the cluster
- Guarantees resources for other services (backend, frontend)
- Enforces fairness across multiple concurrent briefing requests

#### Network Policies

Restrict tool pod network access to only required services:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: tool-isolation
  namespace: doctor-tools
spec:
  podSelector:
    matchLabels:
      role: tool
  policyTypes:
  - Ingress
  - Egress

  # No ingress — tools don't receive traffic
  ingress: []

  egress:
  # Allow DNS resolution
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - port: 53
      protocol: UDP

  # Allow database access
  - to:
    - namespaceSelector:
        matchLabels:
          name: doctor-app
      podSelector:
        matchLabels:
          app: postgres
    ports:
    - port: 5432
      protocol: TCP

  # Block everything else (no internet, no other services)
```

**Security Impact:**
- Tools cannot make arbitrary HTTP requests to internet
- Tools cannot access Redis, message queues, or other services
- Tools can only query the database (read-only service account)
- Reduces attack surface if a tool is compromised

#### Security Context

Lock down container capabilities using securityContext:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: tool-pod
spec:
  securityContext:
    runAsNonRoot: true           # Prevent running as root
    runAsUser: 1000              # Run as UID 1000
    fsGroup: 1000                # Set filesystem group
    seccompProfile:
      type: RuntimeDefault       # Use default seccomp profile

  containers:
  - name: tool
    image: tool:v1
    securityContext:
      readOnlyRootFilesystem: true        # Cannot write to container filesystem
      allowPrivilegeEscalation: false     # Cannot gain more privileges
      capabilities:
        drop: ["ALL"]                     # Drop all Linux capabilities
    volumeMounts:
    - name: tmp
      mountPath: /tmp                     # Only writable directory

  volumes:
  - name: tmp
    emptyDir:
      medium: Memory                      # In-memory tmpfs (wiped on pod deletion)
      sizeLimit: 64Mi
```

**Capabilities Dropped:**
- `CAP_NET_ADMIN`: Cannot modify network interfaces
- `CAP_SYS_ADMIN`: Cannot mount filesystems
- `CAP_SYS_TIME`: Cannot change system clock
- `CAP_KILL`: Cannot kill other processes
- And 30+ more capabilities — see `man capabilities`

#### Pod Security Standards

Apply Kubernetes Pod Security Standards to the namespace:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: doctor-tools
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

**Restricted Policy Enforces:**
- No privileged containers
- No host namespaces (hostNetwork, hostPID, hostIPC)
- No host ports
- No host path volumes
- Must run as non-root
- Must drop all capabilities
- Seccomp profile required

Pods violating these rules will be rejected at admission time.

## Comparison: Agent Isolation Approaches

| Approach | Isolation Level | Startup Time | Cost | K8s Native | Best For |
|----------|----------------|-------------|------|------------|----------|
| K8s Pods/Jobs | Process-level (Linux namespaces, cgroups) | ~1-5s (image cached) | Included in cluster | Yes | Most workloads |
| gVisor (runsc) | Kernel-level (user-space kernel) | ~2-10s | 10-20% CPU overhead | Yes (RuntimeClass) | Untrusted code |
| E2B (external service) | VM-level (Firecracker micro-VM) | ~150ms | $0.01-0.05 per execution | No | Sandboxed code execution |
| Cloudflare Workers | V8 isolate | ~0ms (cold start ~5ms) | $0.15 per million requests | No | Stateless functions |
| Firecracker (self-hosted) | VM-level (micro-VM) | ~125ms | Self-hosted infrastructure | No (requires custom infra) | Multi-tenant SaaS platforms |

### Detailed Comparison

#### K8s Pods/Jobs (Recommended for AI Doctor V2)

**Pros:**
- Native to Kubernetes, no additional tools required
- Easy to debug (kubectl logs, kubectl exec)
- Full control over resource limits and network policies
- Free (part of your K8s cluster cost)

**Cons:**
- Process-level isolation (shared kernel with host)
- Slower startup than VM isolates (1-5 seconds)
- Not suitable for fully untrusted code

**When to Use:**
- Deterministic tools written by your team
- Tools that need database access
- Tools that benefit from K8s orchestration (retries, logs, monitoring)

#### gVisor with runsc

**Pros:**
- Stronger isolation than standard containers (user-space kernel)
- Still K8s-native (use RuntimeClass)
- Good for running LLM-generated code snippets

**Cons:**
- 10-20% CPU overhead for syscall interception
- Slower startup than standard containers
- Some syscalls not implemented (rare edge cases)

**When to Use:**
- Running code generated by LLMs
- Executing user-provided code (medical calculators from doctors)
- Need stronger isolation than standard containers

**Example RuntimeClass:**

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: gvisor
handler: runsc
---
apiVersion: v1
kind: Pod
metadata:
  name: untrusted-tool
spec:
  runtimeClassName: gvisor  # Use gVisor instead of standard runc
  containers:
  - name: tool
    image: tool:v1
```

#### E2B (External Sandboxing Service)

**Pros:**
- Zero infrastructure setup
- Fast VM startup (~150ms)
- Strong isolation (Firecracker micro-VMs)

**Cons:**
- External dependency (vendor lock-in)
- Per-execution pricing (can get expensive at scale)
- Cannot access your database directly (need API gateway)

**When to Use:**
- Proof-of-concept for code execution features
- Low-volume code execution (<1000 executions/day)
- Don't want to manage sandboxing infrastructure

### Which to Use for AI Doctor?

**V2 (Next Iteration):**
- **K8s Jobs** — simple, sufficient isolation for deterministic tools
- Tools: lab threshold checking, drug interaction lookup, medical guideline queries
- All tools written by your team, no LLM-generated code

**V3 (6-12 Months Out):**
- **gVisor** if running LLM-generated code snippets
- Example: "Agent generates Python code to parse a novel lab format"
- Still K8s-native, just swap RuntimeClass

**Alternative (If You Want Zero Ops):**
- **E2B** for code execution sandboxing
- Delegate all sandboxing concerns to external service
- Trade cost for simplicity

## AI Doctor Infrastructure Roadmap

Evolution from external API to local GPU models:

```
V1 (Current — Jan 2026)          V2 (Next — Q2 2026)              V3 (Future — Q4 2026)
────────────────────────────────────────────────────────────────────────────────────────
┌─────────┐                      ┌─────────┐                      ┌─────────┐
│ React   │                      │ React   │                      │ React   │
│ Frontend│                      │ Frontend│                      │ Frontend│
│ (SPA)   │                      │ (SPA)   │                      │ (SPA)   │
└────┬────┘                      └────┬────┘                      └────┬────┘
     │                                │                                │
     │ HTTPS                          │ HTTPS                          │ HTTPS
     │                                │                                │
┌────┴──────────┐              ┌─────┴─────────┐              ┌─────┴─────────┐
│ FastAPI       │              │ FastAPI       │              │ FastAPI       │
│ Backend       │              │ Backend       │              │ Backend       │
│               │              │               │              │               │
│ ┌───────────┐ │              │ ┌───────────┐ │              │ ┌───────────┐ │
│ │ Claude    │ │              │ │ Claude    │ │              │ │ Claude    │ │
│ │ Agent SDK │─┼─→ Claude API │ │ Agent SDK │─┼─→ Claude API │ │ Agent SDK │─┼─→ Claude API
│ └───────────┘ │  (Anthropic) │ │           │ │  (Anthropic) │ │           │ │  (Anthropic)
│               │              │ │ Tool      │ │              │ │ Tool      │ │
│               │              │ │ Dispatch  │ │              │ │ Dispatch  │ │
│               │              │ └─────┬─────┘ │              │ └─────┬─────┘ │
└───────┬───────┘              └───────┼───────┘              └───────┼───────┘
        │                              │                              │
        │                              │ K8s Job                      │ K8s Job (gVisor)
        │                              ↓                              ↓
┌───────┴────────┐             ┌──────────────┐             ┌──────────────┐
│ PostgreSQL     │             │ Tool Pods    │             │ Tool Pods    │
│ (Docker local) │             │ ┌──────────┐ │             │ ┌──────────┐ │
└────────────────┘             │ │Lab Check │ │             │ │Lab Check │ │
                               │ └──────────┘ │             │ │(isolated)│ │
                               │ ┌──────────┐ │             │ └──────────┘ │
                               │ │Drug      │ │             │ ┌──────────┐ │
                               │ │Interact  │ │             │ │LLM Code  │ │
                               │ └──────────┘ │             │ │Executor  │ │
                               └──────┬───────┘             │ └──────────┘ │
                                      │                     └──────┬───────┘
                               ┌──────┴───────┐                   │
                               │ PostgreSQL   │            ┌──────┴───────┐
                               │ (in-cluster) │            │ Cloud SQL    │
                               └──────────────┘            │ (PostgreSQL) │
                                                           └──────┬───────┘
                                                                  │
                                                           ┌──────┴───────┐
                                                           │ GPU Node Pool│
                                                           │ ┌──────────┐ │
                                                           │ │ T4/L4    │ │
                                                           │ │ Spot     │ │
                                                           │ └──────────┘ │
                                                           │ ┌──────────┐ │
                                                           │ │ Embedding│ │
                                                           │ │ Model    │ │
                                                           │ └──────────┘ │
                                                           │ ┌──────────┐ │
                                                           │ │ Local    │ │
                                                           │ │ Medical  │ │
                                                           │ │ LLM      │ │
                                                           │ └──────────┘ │
                                                           └──────────────┘

Infrastructure:                  Infrastructure:                  Infrastructure:
- Docker Compose                - GKE Standard                   - GKE Standard
- Local PostgreSQL              - Artifact Registry              - Cloud SQL (HA)
- Claude API (external)         - Cloud SQL or in-cluster PG    - Artifact Registry
                                - CPU nodes only                 - CPU + GPU node pools
                                - Claude API (external)          - T4 spot (embeddings)
                                                                 - L4 on-demand (inference)
                                                                 - Claude API (primary)

Cost: ~$0/month                 Cost: ~$150-300/month            Cost: ~$500-1000/month
(dev only, API usage separate)  (cluster + managed DB)           (+ GPU when active)
```

### Infrastructure Decision Points

**When to Move from V1 to V2:**
- Deploying to production (real users)
- Need agent tools for deterministic medical logic
- Want to scale beyond single-machine Docker Compose

**When to Move from V2 to V3:**
- Need local embeddings for semantic search (10,000+ documents)
- Want to fine-tune models on proprietary medical data
- Latency requirements demand local inference (<100ms)
- Compliance requires models run on your infrastructure

**Cost Considerations:**
- V1: Free infrastructure (only pay for Claude API usage)
- V2: ~$200/month for GKE + Cloud SQL (3-node cluster)
- V3: +$80-255/month per GPU node when active (scale to zero when idle)

## Key Takeaways

### GPUs Are Expensive — Use Sparingly
- Only add GPUs when you have local model workloads
- Start with T4 spot instances (cheapest at ~$0.11/hr)
- Scale GPU nodes to zero when idle (min-nodes=0)
- Batch embeddings and fine-tuning jobs to minimize GPU hours

### Agent Isolation Starts Simple
- V2: K8s Jobs with resource limits and network policies
- V3: Add gVisor RuntimeClass if running LLM-generated code
- Alternative: E2B for zero-ops code sandboxing

### AI Doctor Doesn't Need GPUs Until V3+
- V1: All AI via Claude API (no local models)
- V2: Agent tools are deterministic logic (no models)
- V3: Local embeddings and medical LLM justify GPU costs

### Kubernetes Provides All Isolation Primitives
- **Jobs**: One-shot tool execution with retries and timeouts
- **ResourceQuotas**: Limit total tool resource consumption
- **NetworkPolicies**: Restrict tool network access
- **SecurityContext**: Lock down container capabilities
- **Pod Security Standards**: Enforce security baseline

### Practical Next Steps for AI Doctor

1. **Stay on V1 for now** (external Claude API, Docker Compose)
2. **When ready for production** (V2):
   - Deploy to GKE Standard cluster
   - Implement tool dispatch with K8s Jobs
   - Add resource quotas and network policies
3. **When local models make sense** (V3):
   - Add GPU node pool with T4 spot instances
   - Deploy embedding model for semantic search
   - Evaluate fine-tuning medical briefing model
4. **Monitor costs**:
   - Set up billing alerts in GCP
   - Track GPU utilization (aim for >60% when active)
   - Scale to zero when idle

The beauty of this roadmap: each step is incremental, with clear cost and capability trade-offs.
