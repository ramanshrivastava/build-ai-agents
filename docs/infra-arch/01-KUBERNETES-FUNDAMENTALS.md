# Kubernetes Fundamentals

**Part 1 of 9: Infrastructure Architecture Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Why Kubernetes Exists](#why-kubernetes-exists)
2. [Cluster Architecture](#cluster-architecture)
3. [Core Kubernetes Objects](#core-kubernetes-objects)
4. [Declarative vs Imperative Management](#declarative-vs-imperative-management)
5. [The Reconciliation Loop](#the-reconciliation-loop)
6. [Quick Reference Table](#quick-reference-table)

---

## Why Kubernetes Exists

### The Container Orchestration Problem

You've containerized your application with Docker. Your FastAPI backend runs in a container, your React frontend runs in another, and PostgreSQL runs in a third. Locally, you use `docker-compose` and everything works beautifully. But now you need to deploy to production. The questions start:

- Which server should run which container?
- What happens when a container crashes?
- How do you deploy a new version without downtime?
- How do containers discover and talk to each other across machines?
- How do you scale from 1 to 10 backend replicas when traffic spikes?
- How do you manage configuration and secrets across environments?

**Manual container management doesn't scale.** You could write bash scripts to SSH into servers, pull images, start containers, configure networking, monitor health checks, and restart failed containers. But this is fragile, error-prone, and doesn't handle the dynamic nature of modern infrastructure.

### What Kubernetes Solves

Kubernetes (K8s) is a **container orchestration platform** that automates the deployment, scaling, and management of containerized applications. It provides:

1. **Scheduling** — Decides which node (server) runs which container based on resource requirements
2. **Scaling** — Automatically adds or removes container replicas based on load
3. **Self-healing** — Restarts failed containers, replaces crashed nodes, kills unresponsive containers
4. **Rolling updates** — Deploys new versions gradually, with automatic rollback on failure
5. **Service discovery** — Containers find each other by name, regardless of which node they're on
6. **Load balancing** — Distributes traffic across healthy container replicas
7. **Configuration management** — Externalizes config and secrets from container images
8. **Storage orchestration** — Mounts persistent storage from local disks, cloud providers, or network storage

### Brief History

Kubernetes is based on **Google Borg**, Google's internal container orchestration system that has run production workloads for over 15 years. In 2014, Google open-sourced Kubernetes and donated it to the **Cloud Native Computing Foundation (CNCF)**. Today, K8s is the de facto standard for container orchestration, with support from every major cloud provider (GCP, AWS, Azure) and a massive ecosystem of tools.

For the AI Doctor Assistant, Kubernetes means we can deploy our FastAPI backend, React frontend, and PostgreSQL database to Google Kubernetes Engine (GKE Autopilot) and get automatic scaling, zero-downtime deployments, and production-grade reliability without writing thousands of lines of infrastructure code.

---

## Cluster Architecture

A Kubernetes cluster consists of two main components: the **control plane** (which manages the cluster) and **worker nodes** (which run application containers).

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CONTROL PLANE                              │
│  (Manages the cluster - typically managed by cloud provider)        │
│                                                                     │
│  ┌──────────────┐   ┌─────────────┐   ┌────────────┐   ┌────────┐ │
│  │  API Server  │   │    etcd     │   │ Scheduler  │   │ Ctrl   │ │
│  │              │   │             │   │            │   │ Manager│ │
│  │  REST API    │◄─►│ Key-Value   │   │ Assigns    │   │        │ │
│  │  Frontend    │   │ Store       │   │ Pods to    │   │ Runs   │ │
│  │  for cluster │   │             │   │ Nodes      │   │ Control│ │
│  │              │   │ (State)     │   │            │   │ Loops  │ │
│  └──────┬───────┘   └─────────────┘   └────────────┘   └────────┘ │
│         │                                                           │
└─────────┼───────────────────────────────────────────────────────────┘
          │
          │  (kubectl, API calls)
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         WORKER NODES                                │
│  (Run application containers)                                       │
│                                                                     │
│  ┌──────────────────────────────────────┐  ┌──────────────────────┐│
│  │           NODE 1                     │  │      NODE 2          ││
│  │                                      │  │                      ││
│  │  ┌────────────┐   ┌──────────────┐  │  │  ┌──────────────┐    ││
│  │  │  kubelet   │   │ kube-proxy   │  │  │  │  kubelet     │    ││
│  │  │            │   │              │  │  │  │              │    ││
│  │  │ Node agent │   │ Network      │  │  │  │ Node agent   │    ││
│  │  │ Manages    │   │ proxy        │  │  │  │              │    ││
│  │  │ Pods       │   │              │  │  │  │              │    ││
│  │  └────┬───────┘   └──────────────┘  │  │  └──────────────┘    ││
│  │       │                              │  │                      ││
│  │       │  ┌───────────────────────┐  │  │  ┌────────────────┐  ││
│  │       └─►│  Container Runtime    │  │  │  │ Container      │  ││
│  │          │  (containerd/Docker)  │  │  │  │ Runtime        │  ││
│  │          └───────┬───────────────┘  │  │  └───┬────────────┘  ││
│  │                  │                   │  │      │               ││
│  │         ┌────────▼─────────┐        │  │  ┌───▼────┐          ││
│  │         │   POD            │        │  │  │  POD   │          ││
│  │         │ ┌──────────────┐ │        │  │  │ ┌────┐ │          ││
│  │         │ │ FastAPI      │ │        │  │  │ │PG  │ │          ││
│  │         │ │ Backend      │ │        │  │  │ │DB  │ │          ││
│  │         │ │ Container    │ │        │  │  │ └────┘ │          ││
│  │         │ └──────────────┘ │        │  │  └────────┘          ││
│  │         └──────────────────┘        │  │                      ││
│  └──────────────────────────────────────┘  └──────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### Control Plane Components

1. **API Server** — The front door to Kubernetes. All operations (kubectl commands, deployments, scaling) go through the API Server. It's a REST API that validates and processes requests, then updates etcd.

2. **etcd** — A distributed key-value store that holds the entire cluster state. Every object you create (pods, services, deployments) is stored here. If etcd data is lost, the cluster forgets everything.

3. **Scheduler** — Watches for newly created Pods that don't have a Node assigned yet. It evaluates resource requirements (CPU, memory), node constraints, and affinity rules, then assigns the Pod to the best-fit Node.

4. **Controller Manager** — Runs control loops that watch the cluster state and make changes to reach the desired state. Examples: Deployment Controller (manages ReplicaSets), Node Controller (detects node failures), Service Controller (creates cloud load balancers).

### Worker Node Components

1. **kubelet** — The agent that runs on every worker node. It receives Pod specifications from the API Server and ensures those containers are running and healthy. It reports node and Pod status back to the control plane.

2. **kube-proxy** — A network proxy that runs on each node. It maintains network rules to allow communication to Pods from inside or outside the cluster. When you create a Service, kube-proxy sets up the routing rules.

3. **Container Runtime** — The software that actually runs containers (containerd, Docker, CRI-O). The kubelet talks to the container runtime via the Container Runtime Interface (CRI).

4. **Pods** — The smallest deployable units in Kubernetes. A Pod wraps one or more containers, shared storage, and network configuration. Containers in a Pod share an IP address and can communicate via localhost.

---

## Core Kubernetes Objects

Kubernetes uses a declarative API model. You define **objects** in YAML files that describe the desired state of your application. Kubernetes constantly works to make the observed state match your desired state.

### Pod

**What it is:** A Pod is the smallest deployable unit in Kubernetes. It represents a single instance of a running process in your cluster. A Pod encapsulates one or more containers, shared storage volumes, a unique network IP, and configuration options.

**Why it exists:** Docker containers are just processes. Kubernetes needs a higher-level abstraction to manage containers with shared resources (network, storage, lifecycle). Pods allow multiple tightly-coupled containers (e.g., app + logging sidecar) to share the same network namespace and volumes.

**AI Doctor Assistant Example:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: doctor-backend
  namespace: doctor-app
  labels:
    app: doctor-backend
    tier: api
spec:
  containers:
  - name: fastapi
    image: gcr.io/my-project/doctor-backend:v2.1.0
    ports:
    - containerPort: 8000
      name: http
    env:
    - name: DATABASE_URL
      value: "postgresql://postgres:5432/doctor"
    - name: ANTHROPIC_API_KEY
      valueFrom:
        secretKeyRef:
          name: ai-credentials
          key: anthropic_key
    resources:
      requests:
        cpu: "500m"
        memory: "512Mi"
      limits:
        cpu: "1000m"
        memory: "1Gi"
```

This Pod runs a single FastAPI backend container. In practice, you rarely create Pods directly—you use higher-level controllers like Deployments.

---

### Deployment

**What it is:** A Deployment manages a set of identical Pods. It creates a ReplicaSet (which ensures a specified number of Pod replicas are running) and provides declarative updates for Pods and ReplicaSets.

**Why it exists:** Manually creating Pods doesn't give you scaling, self-healing, or rolling updates. If a Pod crashes, it stays dead. If you want 3 replicas, you'd have to create 3 Pod YAML files. Deployments solve this by managing Pod lifecycles automatically.

**AI Doctor Assistant Example:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: doctor-backend
  namespace: doctor-app
  labels:
    app: doctor-backend
spec:
  replicas: 2  # Run 2 backend instances
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # Max 1 extra pod during update
      maxUnavailable: 0  # Keep all old pods until new ones are ready
  selector:
    matchLabels:
      app: doctor-backend
  template:
    metadata:
      labels:
        app: doctor-backend
    spec:
      containers:
      - name: fastapi
        image: gcr.io/my-project/doctor-backend:v2.1.0
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: backend-config
        - secretRef:
            name: ai-credentials
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

When you update the image tag (e.g., to `v2.2.0`), Kubernetes performs a rolling update: it creates new Pods with the new version, waits for them to be healthy, then terminates old Pods. Zero downtime.

---

### Service

**What it is:** A Service provides a stable network endpoint for a set of Pods. Pods are ephemeral—they get created, destroyed, and rescheduled with new IP addresses. Services provide a consistent DNS name and IP address that routes traffic to healthy Pods.

**Why it exists:** Without Services, clients would need to track the IP addresses of all backend Pods and handle Pod restarts themselves. Services abstract Pod IP changes and provide load balancing across replicas.

**AI Doctor Assistant Example:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: doctor-backend
  namespace: doctor-app
spec:
  type: ClusterIP  # Internal only (not exposed outside cluster)
  selector:
    app: doctor-backend  # Route to Pods with this label
  ports:
  - name: http
    protocol: TCP
    port: 8000        # Service port
    targetPort: 8000  # Container port
```

Now any Pod in the cluster can reach the backend via `http://doctor-backend.doctor-app.svc.cluster.local:8000`. Kubernetes load-balances across both backend Pod replicas.

**Service Types:**

- **ClusterIP** (default) — Internal only, accessible within the cluster
- **NodePort** — Exposes the Service on each Node's IP at a static port
- **LoadBalancer** — Creates an external load balancer (cloud provider-specific)
- **ExternalName** — Maps the Service to a DNS name (e.g., external database)

---

### Namespace

**What it is:** Namespaces provide virtual cluster isolation within a single physical cluster. They're a way to divide cluster resources between multiple users, teams, or environments.

**Why it exists:** Without namespaces, all resources live in a flat global space. Name collisions are inevitable. Namespaces allow you to create `doctor-backend` in `dev`, `staging`, and `prod` namespaces without conflicts.

**AI Doctor Assistant Example:**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: doctor-app
  labels:
    environment: production
    team: ai-health
```

All our resources (Deployments, Services, ConfigMaps) are created in the `doctor-app` namespace. You can apply resource quotas and network policies per namespace.

---

### ConfigMap

**What it is:** A ConfigMap stores non-sensitive configuration data as key-value pairs. Pods can consume ConfigMaps as environment variables, command-line arguments, or configuration files mounted as volumes.

**Why it exists:** Hardcoding configuration in container images makes images environment-specific (you'd need separate images for dev, staging, prod). ConfigMaps externalize configuration, so the same image runs in all environments with different configs.

**AI Doctor Assistant Example:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: backend-config
  namespace: doctor-app
data:
  AI_MODEL: "claude-opus-4-6"
  DEBUG: "false"
  LOG_LEVEL: "info"
  MAX_RETRIES: "3"
  CORS_ORIGINS: "https://doctor.example.com"
```

The Deployment references this ConfigMap:

```yaml
envFrom:
- configMapRef:
    name: backend-config
```

All key-value pairs from the ConfigMap become environment variables in the container. To update configuration, edit the ConfigMap and restart the Pods (or configure automatic rollouts).

---

### Secret

**What it is:** A Secret is like a ConfigMap, but for sensitive data (passwords, API keys, certificates). Secrets are base64-encoded (not encrypted by default) and can be encrypted at rest if configured.

**Why it exists:** Storing secrets in ConfigMaps exposes them in plaintext. Secrets provide a dedicated API object with access controls and integration with secret management tools (e.g., Google Secret Manager, HashiCorp Vault).

**AI Doctor Assistant Example:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ai-credentials
  namespace: doctor-app
type: Opaque
data:
  anthropic_key: YW50aHJvcGljX2FwaV9rZXk=  # base64-encoded
  database_password: cG9zdGdyZXNfcGFzcw==
```

The Deployment references specific keys:

```yaml
env:
- name: ANTHROPIC_API_KEY
  valueFrom:
    secretKeyRef:
      name: ai-credentials
      key: anthropic_key
```

**Security Note:** Secrets in YAML files should never be committed to git. Use tools like Sealed Secrets, External Secrets Operator, or cloud provider secret managers to inject secrets at runtime.

---

### Ingress

**What it is:** An Ingress exposes HTTP(S) routes from outside the cluster to Services within the cluster. It provides load balancing, SSL termination, and name-based virtual hosting.

**Why it exists:** Without Ingress, you'd need a LoadBalancer Service for every application, which creates a separate cloud load balancer (expensive). Ingress consolidates routing rules into a single entry point.

**AI Doctor Assistant Example:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: doctor-ingress
  namespace: doctor-app
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - doctor.example.com
    secretName: doctor-tls-cert
  rules:
  - host: doctor.example.com
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: doctor-backend
            port:
              number: 8000
      - path: /
        pathType: Prefix
        backend:
          service:
            name: doctor-frontend
            port:
              number: 80
```

This Ingress routes:

- `https://doctor.example.com/api/*` → backend Service (FastAPI)
- `https://doctor.example.com/*` → frontend Service (React SPA)

It terminates TLS using a certificate from cert-manager and Let's Encrypt.

---

### PersistentVolume (PV) & PersistentVolumeClaim (PVC)

**What it is:** A PersistentVolume is a piece of storage in the cluster (disk, NFS, cloud block storage). A PersistentVolumeClaim is a request for storage by a user. PVs are cluster-wide resources; PVCs are namespace-scoped.

**Why it exists:** Container filesystems are ephemeral—data is lost when a container restarts. For stateful applications (databases, file uploads), you need persistent storage that survives Pod restarts and can be moved between nodes.

**AI Doctor Assistant Example:**

PersistentVolumeClaim (what the Pod requests):

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: doctor-app
spec:
  accessModes:
  - ReadWriteOnce  # Single node read-write
  resources:
    requests:
      storage: 20Gi
  storageClassName: pd-ssd  # GKE persistent disk SSD
```

StatefulSet (for PostgreSQL) references the PVC:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: doctor-app
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:16
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: pd-ssd
      resources:
        requests:
          storage: 20Gi
```

When the Pod restarts, Kubernetes attaches the same PV to the new Pod. PostgreSQL data persists.

---

### Labels & Selectors

**What it is:** Labels are key-value pairs attached to objects (Pods, Services, Nodes). Selectors are queries that match objects based on labels. Labels are the glue that connects Kubernetes objects.

**Why it exists:** Kubernetes needs a flexible way for objects to reference each other. Services need to find Pods. Deployments need to manage Pods. Labels provide a loose coupling mechanism—add a label to a Pod, and Services/Deployments automatically pick it up.

**AI Doctor Assistant Example:**

```yaml
# Deployment creates Pods with these labels
apiVersion: apps/v1
kind: Deployment
metadata:
  name: doctor-backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: doctor-backend  # Deployment manages Pods with this label
  template:
    metadata:
      labels:
        app: doctor-backend
        tier: api
        version: v2
---
# Service selects Pods with this label
apiVersion: v1
kind: Service
metadata:
  name: doctor-backend
spec:
  selector:
    app: doctor-backend  # Routes traffic to Pods with this label
  ports:
  - port: 8000
```

**Common Label Patterns:**

- `app: doctor-backend` — Application name
- `tier: api` — Layer in the stack (frontend, api, database)
- `environment: production` — Environment (dev, staging, prod)
- `version: v2.1.0` — Application version (useful for canary deployments)

You can query objects by label:

```bash
kubectl get pods -l app=doctor-backend
kubectl get pods -l tier=api,environment=production
```

---

## Declarative vs Imperative Management

Kubernetes supports two ways to manage resources: **imperative** (commands) and **declarative** (YAML files).

### Imperative (Not Recommended for Production)

Imperative commands create resources directly via kubectl:

```bash
# Create a deployment
kubectl create deployment doctor-backend \
  --image=gcr.io/my-project/doctor-backend:v2.1.0

# Expose it as a service
kubectl expose deployment doctor-backend \
  --type=ClusterIP --port=8000

# Scale it
kubectl scale deployment doctor-backend --replicas=3
```

**Problems:**

- **Not reproducible** — Commands are not saved. If you need to recreate the cluster, you have to remember what you typed.
- **No version control** — You can't track changes in git or review them in pull requests.
- **Drift** — The cluster state drifts from documentation. Debugging "why is this configured this way?" is impossible.
- **No GitOps** — Tools like ArgoCD and Flux require declarative manifests.

### Declarative (Best Practice)

Declarative management uses YAML files to define the desired state:

```yaml
# manifests/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: doctor-backend
  namespace: doctor-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: doctor-backend
  template:
    metadata:
      labels:
        app: doctor-backend
    spec:
      containers:
      - name: fastapi
        image: gcr.io/my-project/doctor-backend:v2.1.0
        ports:
        - containerPort: 8000
```

Apply the manifest:

```bash
kubectl apply -f manifests/backend-deployment.yaml
```

**Benefits:**

- **Reproducible** — Run `kubectl apply -f manifests/` in any cluster and get the same result.
- **Version controlled** — YAML files live in git. Every change has a commit, author, and review.
- **Auditable** — Git history shows who changed what and when.
- **GitOps-friendly** — Tools like ArgoCD watch a git repo and automatically sync changes to the cluster.
- **Idempotent** — Run `kubectl apply` multiple times, and the cluster converges to the desired state.

### Why Declarative Wins

In production, your infrastructure is code. You want the same rigor for Kubernetes manifests as for application code: version control, code review, automated testing, and rollback capability. Declarative management makes this possible.

**Golden Rule:** If it's not in git, it doesn't exist.

---

## The Reconciliation Loop

Kubernetes operates on a **reconciliation loop** model. You declare the desired state (via YAML), and Kubernetes constantly works to make the observed state match the desired state.

### The Loop in Action

```
                    ┌──────────────────────────┐
                    │  USER / CI/CD PIPELINE   │
                    └────────────┬─────────────┘
                                 │
                                 │ kubectl apply -f deployment.yaml
                                 ▼
                    ┌──────────────────────────┐
                    │       API SERVER         │
                    │  Validates, persists to  │
                    │        etcd              │
                    └────────────┬─────────────┘
                                 │
                                 │ Watch for changes
                                 ▼
                    ┌──────────────────────────┐
                    │      CONTROLLER          │
                    │  (e.g., Deployment       │
                    │   Controller)            │
                    └────────────┬─────────────┘
                                 │
                                 │ Compare desired vs observed
                                 │
                ┌────────────────┴────────────────┐
                │                                 │
                ▼                                 ▼
    ┌────────────────────┐            ┌────────────────────┐
    │ DESIRED STATE      │            │ OBSERVED STATE     │
    │ (from YAML)        │            │ (from cluster)     │
    │                    │            │                    │
    │ replicas: 3        │            │ running pods: 2    │
    │ image: v2.1.0      │            │ image: v2.0.0      │
    └────────────────────┘            └────────────────────┘
                │                                 │
                └────────────┬────────────────────┘
                             │
                             │ State differs
                             ▼
                ┌──────────────────────────┐
                │   TAKE ACTION            │
                │  - Create 1 new Pod      │
                │  - Update 2 existing Pods│
                └────────────┬─────────────┘
                             │
                             │ Execute action
                             ▼
                ┌──────────────────────────┐
                │   OBSERVED STATE         │
                │   (updated)              │
                │                          │
                │  running pods: 3         │
                │  image: v2.1.0           │
                └────────────┬─────────────┘
                             │
                             │ Loop continues (every 10s)
                             │
                             ▼
                     (back to compare)
```

### How It Works

1. **User submits desired state** — You run `kubectl apply -f deployment.yaml`. The API Server validates the YAML, authenticates/authorizes you, and writes the desired state to etcd.

2. **Controller watches for changes** — The Deployment Controller watches the API Server for changes to Deployment objects. It sees your new Deployment.

3. **Compare desired vs observed** — The controller queries the current state (how many Pods are running, what versions) and compares it to the desired state (replicas: 3, image: v2.1.0).

4. **Take action to reconcile** — If the states differ, the controller takes corrective action:
   - Too few Pods? Create more.
   - Wrong image version? Update Pods via rolling update.
   - Pod crashed? Create a replacement.

5. **Loop repeats** — Controllers run this loop continuously (typically every 10 seconds). If someone manually deletes a Pod, the controller detects it and creates a replacement.

### Concrete Example: Scaling from 2 to 3 replicas

```bash
# Current state: 2 backend Pods running
kubectl get pods -l app=doctor-backend
# doctor-backend-abc123  Running
# doctor-backend-def456  Running

# Update the Deployment YAML: replicas: 2 → replicas: 3
kubectl apply -f deployment.yaml
# deployment.apps/doctor-backend configured

# Deployment Controller detects the change
# Compares desired (3) vs observed (2)
# Creates 1 new Pod

kubectl get pods -l app=doctor-backend
# doctor-backend-abc123  Running
# doctor-backend-def456  Running
# doctor-backend-ghi789  ContainerCreating  ← New Pod

# Wait a few seconds
kubectl get pods -l app=doctor-backend
# doctor-backend-abc123  Running
# doctor-backend-def456  Running
# doctor-backend-ghi789  Running  ← Healthy

# Desired state achieved. Controller goes idle until next change.
```

### Why This Matters

The reconciliation loop is Kubernetes' superpower. You describe what you want (3 replicas, image v2.1.0) and Kubernetes figures out how to get there. If something breaks (node crashes, Pod gets killed), Kubernetes automatically fixes it without you lifting a finger.

This is fundamentally different from traditional ops, where you'd write a script to do something once (imperative). Kubernetes continuously ensures your desired state is maintained (declarative).

---

## Quick Reference Table

| Object | Kind | Purpose | kubectl Shortname |
|--------|------|---------|-------------------|
| **Pod** | `Pod` | Smallest deployable unit; wraps one or more containers | `po` |
| **Deployment** | `Deployment` | Manages ReplicaSets and Pods; handles rolling updates | `deploy` |
| **ReplicaSet** | `ReplicaSet` | Ensures a specified number of Pod replicas are running | `rs` |
| **StatefulSet** | `StatefulSet` | Like Deployment, but for stateful apps (stable network IDs, ordered deployment) | `sts` |
| **DaemonSet** | `DaemonSet` | Runs a Pod on every node (e.g., logging agent, monitoring) | `ds` |
| **Job** | `Job` | Runs a Pod to completion (batch processing) | `job` |
| **CronJob** | `CronJob` | Runs Jobs on a schedule (like cron) | `cj` |
| **Service** | `Service` | Stable network endpoint for a set of Pods | `svc` |
| **Ingress** | `Ingress` | HTTP(S) routing and TLS termination | `ing` |
| **ConfigMap** | `ConfigMap` | Non-sensitive configuration data | `cm` |
| **Secret** | `Secret` | Sensitive data (base64-encoded) | `secret` |
| **PersistentVolume** | `PersistentVolume` | Cluster-wide storage resource | `pv` |
| **PersistentVolumeClaim** | `PersistentVolumeClaim` | Request for storage by a user | `pvc` |
| **StorageClass** | `StorageClass` | Defines types of storage (e.g., SSD, HDD) | `sc` |
| **Namespace** | `Namespace` | Virtual cluster isolation | `ns` |
| **ServiceAccount** | `ServiceAccount` | Identity for Pods (used for RBAC) | `sa` |
| **Role** | `Role` | Namespace-scoped permissions | `role` |
| **RoleBinding** | `RoleBinding` | Grants Role permissions to users/ServiceAccounts | `rolebinding` |
| **ClusterRole** | `ClusterRole` | Cluster-wide permissions | `clusterrole` |
| **ClusterRoleBinding** | `ClusterRoleBinding` | Grants ClusterRole permissions cluster-wide | `clusterrolebinding` |
| **HorizontalPodAutoscaler** | `HorizontalPodAutoscaler` | Auto-scales Pods based on CPU/memory | `hpa` |
| **NetworkPolicy** | `NetworkPolicy` | Firewall rules for Pods | `netpol` |

### Common kubectl Commands

```bash
# Get resources
kubectl get pods                    # List Pods
kubectl get pods -o wide            # Show node placement and IPs
kubectl get pods -l app=backend     # Filter by label
kubectl get all -n doctor-app       # All resources in namespace

# Describe resources (detailed info)
kubectl describe pod doctor-backend-abc123
kubectl describe deployment doctor-backend

# Logs
kubectl logs doctor-backend-abc123           # Current logs
kubectl logs doctor-backend-abc123 -f        # Follow logs (tail -f)
kubectl logs doctor-backend-abc123 --previous # Logs from crashed container

# Execute commands in a Pod
kubectl exec -it doctor-backend-abc123 -- /bin/bash
kubectl exec doctor-backend-abc123 -- env

# Apply/Delete manifests
kubectl apply -f deployment.yaml
kubectl apply -f manifests/        # Apply all YAML files in directory
kubectl delete -f deployment.yaml
kubectl delete pod doctor-backend-abc123

# Edit resources (opens editor)
kubectl edit deployment doctor-backend

# Scale
kubectl scale deployment doctor-backend --replicas=5

# Rollout management
kubectl rollout status deployment doctor-backend
kubectl rollout history deployment doctor-backend
kubectl rollout undo deployment doctor-backend  # Rollback to previous version
```

---

## Summary

Kubernetes is a powerful container orchestration platform that automates the deployment, scaling, and management of containerized applications. For the AI Doctor Assistant project, Kubernetes will:

- Run multiple replicas of our FastAPI backend for high availability
- Automatically restart crashed containers
- Handle zero-downtime deployments when we push new versions
- Provide service discovery so the frontend can find the backend
- Manage configuration and secrets securely
- Integrate with GKE Autopilot for managed infrastructure

The core mental model is **desired state + reconciliation loop**. You declare what you want in YAML, and Kubernetes continuously works to make it happen. This declarative approach makes infrastructure reproducible, version-controlled, and GitOps-friendly.

In the next document, we'll dive into GKE-specific concepts: Autopilot mode, Workload Identity, Cloud SQL integration, and GKE vs standard Kubernetes differences.

---

**Next:** [02-GKE-ARCHITECTURE.md](./02-GKE-ARCHITECTURE.md) — Google Kubernetes Engine specifics and Autopilot mode
