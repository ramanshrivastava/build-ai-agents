# Infrastructure & Kubernetes Learning Guide

## What This Documentation Is For

This is a **learn-first, deploy-later** educational series about Kubernetes, Google Kubernetes Engine (GKE), and deploying the AI Doctor Assistant application to Google Cloud Platform (GCP).

These documents are written for developers who:

- Understand Docker basics (building images, running containers, docker-compose)
- Are new to Kubernetes and want to understand it deeply before deploying
- Need to validate infrastructure knowledge or prepare for production deployment decisions
- Want to know **why** things work, not just **how** to copy-paste commands

The series progresses from fundamental concepts through Kubernetes internals, GKE specifics, tooling ecosystem, application architecture mapping, CI/CD pipelines, advanced capabilities (GPU workloads, agent isolation), nginx and Ingress controller patterns, security and service discovery, real-world deployment alongside an existing portfolio, managed database internals, and a knowledge check with detailed answers.

**This is not a quick-start guide.** If you want to deploy immediately without understanding the underlying systems, this is not the right resource. These documents prioritize depth over speed.

## Prerequisites

Before reading this series, you should have:

- **Docker Basics**: Built images with Dockerfiles, run containers, used docker-compose for multi-service apps
- **Linux CLI Familiarity**: Comfortable with bash, environment variables, file permissions, basic networking commands
- **Basic Networking**: Understand ports, DNS resolution, HTTP requests, load balancing concepts
- **Git & GitHub**: Version control, branching, pull requests, GitHub Actions awareness
- **AI Doctor Assistant**: Have the app running locally via docker-compose (backend + frontend + PostgreSQL)

You do NOT need prior Kubernetes experience. These docs start from first principles.

## Recommended Reading Order

| Document | Title | Description |
|----------|-------|-------------|
| **00-OVERVIEW.md** | This overview | Start here — explains series structure, prerequisites, conventions |
| **01-K8S-FUNDAMENTALS.md** | Kubernetes Fundamentals | Core concepts: Pods, Deployments, Services, ConfigMaps, Secrets |
| **02-K8S-INTERNALS.md** | Kubernetes Internals | Control plane, etcd, scheduler, controllers — what happens on `kubectl apply` |
| **03-GKE-GCP.md** | GKE & Google Cloud Platform | Managed Kubernetes, Autopilot vs Standard, GCP services, pricing models |
| **04-TOOL-ECOSYSTEM.md** | Tool Ecosystem | gcloud, kubectl, k9s, Helm, Kustomize, ArgoCD — when to use each |
| **05-APP-ON-K8S.md** | AI Doctor on Kubernetes | Map AI Doctor architecture to K8s manifests and design decisions |
| **06-DEPLOYMENT-PIPELINE.md** | Deployment Pipeline | Dockerfiles, multi-stage builds, GitHub Actions CI/CD, Artifact Registry |
| **07-GPU-AGENTS.md** | GPU & Agent Isolation | Future: GPU nodes for local models, agent workload isolation strategies |
| **08-KNOWLEDGE-CHECK.md** | Knowledge Check | 55+ questions across fundamentals, architecture, debugging, security |
| **09-LOCAL-DEV-AND-IAC.md** | Local Dev & Infrastructure as Code | minikube, kind, Skaffold for local K8s; Terraform vs Pulumi for IaC |
| **10-NGINX-PROXIES-AND-INGRESS.md** | Nginx, Proxies & Ingress | Web servers vs app servers, nginx deep dive, Ingress controllers, VM-to-K8s pattern shift |
| **11-SECURITY-DISCOVERY-AND-WHY-K8S.md** | Security, Discovery & Why K8s | VM vs K8s tradeoffs, 5-layer security model, service discovery, deployment platform comparison |
| **12-DEPLOYING-ALONGSIDE-PORTFOLIO.md** | Deploying Alongside a Portfolio | Subdomain architecture, deployment target comparison, managed database internals (VMs vs K8s) |
| **[MERMAID-CHEATSHEET.md](../tooling/MERMAID-CHEATSHEET.md)** | Mermaid Diagramming Cheatsheet | Quick reference for creating architecture diagrams — syntax, gotchas, 19 diagram types with infra-themed examples (moved to `docs/tooling/`) |

**Suggested path for first-time readers**: Read 00 → 01 → 02 → 03 in sequence to build foundational understanding. Then read 04 (tools) and 05 (app mapping) to see how theory applies to AI Doctor. Read 06 when ready to implement CI/CD. Read 07 for advanced planning. Read 09 for local K8s testing and IaC tool selection. Read 10 to understand how nginx, reverse proxies, and Ingress controllers fit together in K8s deployments. Read 11 for security hardening, service discovery, and an honest comparison of when K8s is (and is not) the right tool. Read 12 for real-world deployment decisions (deploying alongside a portfolio, managed database internals, cost-optimized architecture). Use 08 for self-assessment and knowledge validation.

**Suggested path for knowledge check**: Read 01 → 02 → 08, using 08 questions to identify gaps, then revisit relevant sections in 01-07. Read 09 for Terraform vs Pulumi comparison (a commonly tested topic). Read 10 for nginx/Ingress questions (frequently relevant in deployment contexts). Read 11 for security layer questions, NetworkPolicy design, and "when would you use K8s vs a simpler alternative" discussions. Read 12 for managed database internals (why data planes run on VMs) and deployment architecture questions.

## Glossary

### A-D

**Autopilot**: GKE's fully-managed mode where Google provisions and manages nodes automatically based on Pod resource requests. Contrast with Standard mode where you configure node pools manually.

**Cluster**: A set of worker nodes (VMs) running containerized applications, managed by a control plane. The fundamental unit of Kubernetes infrastructure.

**ConfigMap**: Kubernetes object for storing non-sensitive configuration data (environment variables, config files) separate from container images.

**Container Runtime**: Software that runs containers on a node (containerd, CRI-O). Pulls images, starts/stops containers, manages container lifecycle.

**Control Plane**: The brains of a Kubernetes cluster. Runs API server, scheduler, controller manager, and etcd. In GKE, Google manages this entirely.

**CRD (Custom Resource Definition)**: Extends Kubernetes API with custom object types. Allows tools like Cert Manager or Istio to define their own resources (Certificate, VirtualService).

**DaemonSet**: Ensures a copy of a Pod runs on every node (or a subset of nodes). Used for node-level services like log collectors, monitoring agents.

### D-N

**Deployment**: Manages a replicated set of Pods with declarative updates. Handles rolling updates, rollbacks, scaling. The primary way to run stateless apps.

**etcd**: Distributed key-value store that holds all cluster state. The source of truth for Kubernetes. Control plane reads/writes all data here.

**GKE (Google Kubernetes Engine)**: Google's managed Kubernetes service. Handles control plane, node provisioning, upgrades, monitoring integration.

**Helm**: Package manager for Kubernetes. Uses "charts" (templated YAML) to deploy complex applications. Think apt/yum for K8s.

**HPA (Horizontal Pod Autoscaler)**: Automatically scales the number of Pods based on CPU, memory, or custom metrics.

**Ingress**: Exposes HTTP/HTTPS routes from outside the cluster to Services inside. Acts as Layer 7 load balancer with path-based routing, TLS termination.

### J-P

**Job**: Creates one or more Pods that run to completion (batch processing, data migration). Ensures tasks complete successfully.

**Kustomize**: Configuration management tool built into kubectl. Uses overlays to customize base YAML for different environments (dev, staging, prod).

**Namespace**: Virtual cluster partition for organizing resources. Isolates teams, apps, or environments (dev/prod) within a single cluster.

**Node**: A worker machine (VM or physical) that runs Pods. Contains kubelet (node agent), container runtime, kube-proxy (networking).

### P-S

**PersistentVolume (PV)**: Cluster-wide storage resource (disk, NFS, cloud block storage). Lifecycle independent of Pods.

**PersistentVolumeClaim (PVC)**: Request for storage by a Pod. Binds to a PV. Separates consumption (PVC) from provisioning (PV).

**Pod**: Smallest deployable unit in Kubernetes. One or more containers sharing network/storage, scheduled together on a node.

**ReplicaSet**: Ensures a specified number of identical Pods are running. Usually managed by Deployments (you rarely create ReplicaSets directly).

**Secret**: Like ConfigMap but for sensitive data (passwords, API keys, TLS certs). Base64-encoded, can be encrypted at rest in etcd.

**Service**: Stable network endpoint for a set of Pods. Provides load balancing, DNS name, and abstraction over Pod IP changes.

### S-W

**StatefulSet**: Like Deployment but for stateful apps (databases). Provides stable network IDs, ordered deployment, persistent storage per Pod.

**Worker Node**: See Node. The machines that run your application Pods. Managed by the control plane.

## Conventions Used

### Formatting

**Code Blocks**: Shell commands, YAML manifests, and configuration files appear in fenced code blocks with language hints:

```bash
# Example command
kubectl apply -f deployment.yaml
```

```yaml
# Example manifest
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
```

**Inline Code**: Commands, file paths, and technical terms appear in `backticks` (e.g., `kubectl`, `/etc/kubernetes/manifests`, `ClusterIP`).

**Tables**: Used for comparisons (Autopilot vs Standard, Service types), command references, and structured lists.

**ASCII Diagrams**: Architecture flows, component relationships, and deployment topology use text-based diagrams for clarity and searchability.

### AI Doctor Callouts

Examples specific to the AI Doctor Assistant app use this format:

```
AI DOCTOR EXAMPLE:
The backend Pod runs FastAPI with uvicorn, connects to PostgreSQL
via a Service (postgres-service), and mounts a Secret for the database
password and Claude API key.
```

These ground abstract concepts in the actual application you'll deploy.

### Emphasis Patterns

- **Bold**: Key terms on first mention, important warnings, critical concepts.
- *Italics*: Emphasis within explanations, contrasts (e.g., "Autopilot is *fully-managed* while Standard is *self-configured*").
- ALL CAPS: Reserved for acronyms (GKE, PVC, HPA) and environment variables (DATABASE_URL, CLAUDE_API_KEY).

### Conceptual Progression

Each document builds on previous knowledge:

- **Fundamentals (01)**: What objects exist, how they relate
- **Internals (02)**: How those objects are implemented under the hood
- **GKE (03)**: How Google's managed service changes the operational model
- **Tools (04)**: What you use to interact with and deploy to clusters
- **Application (05)**: How AI Doctor maps to K8s concepts
- **Pipeline (06)**: How to automate deployment
- **Advanced (07)**: Future capabilities and architectural evolution
- **Local Dev & IaC (09)**: Local K8s testing tools and infrastructure provisioning
- **Nginx & Ingress (10)**: How web servers, app servers, and Ingress controllers work together in K8s
- **Security, Discovery & Why K8s (11)**: VM vs K8s tradeoffs, 5-layer security, service discovery, deployment comparison
- **Deploying Alongside a Portfolio (12)**: Real-world deployment, subdomain architecture, managed database internals
- **Knowledge Check (08)**: Test and validate understanding

Foundational knowledge is not repeated. Document 05 assumes you understand Pods and Services from 01, and control plane flow from 02.

### Learning Objectives

Each document (except 00 and 08) begins with explicit learning objectives:

- What you'll understand after reading
- Key mental models to internalize
- Common misconceptions to avoid

Document 08 inverts this: questions test whether you achieved those objectives.

### Practical Commands

Where relevant, documents include:

- **Example commands** with expected output
- **Common errors** and how to debug them
- **Verification steps** to confirm understanding

These are illustrative, not exhaustive reference material. For complete CLI documentation, see official kubectl/gcloud references.

### Design Decisions

Documents 05-07 explicitly call out **why** certain architectural choices are made:

- Why StatefulSet for PostgreSQL (stable network ID, persistent storage)
- Why Autopilot over Standard (reduced ops burden, cost optimization)
- Why in-cluster PostgreSQL instead of Cloud SQL (learning path, cost control for dev)

Understanding the tradeoffs prepares you to make different choices for production workloads.

## How to Use This Series

### For Learning

1. **Read sequentially** through 01-03 to build mental models of how Kubernetes works.
2. **Experiment locally** with Minikube or kind (local K8s) to test concepts from 01-02.
3. **Read 04** to understand the tool landscape before jumping into GKE.
4. **Read 05-06** when ready to deploy AI Doctor, not before. Theory first, application second.
5. **Read 09** to understand local K8s testing (minikube, Skaffold) and IaC tools (Terraform, Pulumi).
6. **Read 10** to understand how nginx, reverse proxies, and Ingress controllers work together in Kubernetes.
7. **Read 11** to understand when K8s is the right choice, how to secure a cluster (5 layers), and how service discovery works.
8. **Read 12** to see how everything comes together: deploying AI Doctor alongside a portfolio, choosing deployment targets, and understanding managed database internals.
9. **Use 08** as a self-assessment tool after reading 01-07 and 09-12.

### For Deployment

1. Ensure you've read **01-03** to understand what GKE is doing on your behalf.
2. Read **04** to choose tooling (kubectl + Kustomize recommended for AI Doctor).
3. Work through **05-06** to build Dockerfiles, manifests, and CI/CD pipeline.
4. Read **10** to understand how nginx, uvicorn, and Ingress controllers are configured in each pod.
5. Read **11** for security hardening (NetworkPolicies, RBAC, pod security) and service discovery patterns.
6. Reference **03** for GCP-specific details (Artifact Registry, Workload Identity).
7. Read **07** only when planning GPU workloads or advanced agent isolation.
8. Read **12** for practical deployment decisions: subdomain setup, cost-optimized architecture, and when to use managed databases vs in-cluster.

### For Knowledge Validation

1. Read **01-02** for fundamentals and internals.
2. Skim **03-04** for GKE and tooling awareness.
3. Read **11** for security (RBAC, NetworkPolicies, pod security), service discovery, and "when to use K8s vs alternatives" — all important practical topics.
4. Work through **08** questions, using earlier docs to fill knowledge gaps.
5. Focus on **why** questions in 08 (e.g., "Why use StatefulSet for databases?") over **what** questions.

### For Reference

- **01**: Quick lookup for K8s object types (Pod, Service, ConfigMap, etc.)
- **03**: GKE pricing, node types, GCP service comparison
- **04**: Tool decision matrix (when to use Helm vs Kustomize)
- **05**: AI Doctor architecture diagram and manifest examples
- **10**: nginx configuration, Ingress controller comparison, what runs in each pod
- **11**: Security checklist, NetworkPolicy examples, service discovery DNS patterns, deployment platform comparison
- **12**: Deployment target comparison, managed database architecture diagrams, portfolio integration patterns
- **08**: Knowledge check question bank for review

## What This Series Does NOT Cover

- **Multi-cluster management**: Focuses on single GKE cluster for AI Doctor
- **Service meshes**: Istio, Linkerd mentioned briefly in 11, not deep-dived (overkill for this app)
- **Advanced networking**: CNI plugins not deep-dived; NetworkPolicies covered in 11
- **Cluster federation**: Out of scope for single-cluster deployment
- **On-premises Kubernetes**: GKE-focused; kubeadm, Rancher, k3s not covered
- **Windows containers**: Linux containers only
- **Kubernetes the Hard Way**: Assumes managed GKE, not manual cluster bootstrapping

For these topics, see official Kubernetes documentation or specialized guides.

## Document Maintenance

These documents reflect:

- **Kubernetes**: 1.31+ (GKE Autopilot default as of 2025)
- **GKE**: Autopilot mode features as of January 2025
- **AI Doctor**: V1 complete (FastAPI, React 19, PostgreSQL), V2 in planning

As the app evolves (V2: agent tools, V3: GPU support), documents 05-07 will be updated. Core concepts in 01-04 remain stable across Kubernetes versions.

---

**Next Steps**: Proceed to `01-K8S-FUNDAMENTALS.md` to begin learning Kubernetes core concepts, or jump to `08-KNOWLEDGE-CHECK.md` to assess your current knowledge level.
