# Kubernetes Internals — How K8s Works Under the Hood

**Document 02 of 11** — AI Doctor Assistant Infrastructure Series
**Target Platform:** GKE Autopilot
**Application:** FastAPI + React 19 + PostgreSQL 16

---

## Table of Contents

1. [Introduction](#introduction)
2. [Control Plane Components](#control-plane-components)
3. [Control Plane Architecture](#control-plane-architecture)
4. [Node Components](#node-components)
5. [Node Architecture](#node-architecture)
6. [Request Flow: kubectl apply to Running Container](#request-flow-kubectl-apply-to-running-container)
7. [Kubernetes Networking Model](#kubernetes-networking-model)
8. [DNS in Kubernetes](#dns-in-kubernetes)
9. [Recap and Key Takeaways](#recap-and-key-takeaways)

---

## Introduction

Understanding Kubernetes internals is critical for debugging production issues, optimizing cluster performance, and making informed architectural decisions. This document dissects how Kubernetes works under the hood, tracing the journey from a kubectl command to running containers.

**Why this matters for AI Doctor Assistant:**
- Debugging deployment failures requires understanding the scheduler and kubelet
- Performance tuning needs insight into how the API server and etcd scale
- Network troubleshooting depends on grasping the CNI plugin and kube-proxy behavior
- HA planning requires knowing what happens when control plane components fail

---

## Control Plane Components

The **control plane** is the brain of the Kubernetes cluster. It makes global decisions about the cluster state (scheduling, detecting/responding to events) and maintains the desired state declared in your YAML manifests.

### API Server (kube-apiserver)

**What it does:**
The API server is the front door to the cluster. Every interaction with Kubernetes—whether from kubectl, internal controllers, or external systems—goes through the API server. It exposes a RESTful HTTP/HTTPS API.

**Key responsibilities:**
- Serves the Kubernetes API (read/write cluster state)
- Authenticates requests (certificates, tokens, OIDC)
- Authorizes requests (RBAC checks)
- Runs admission controllers (mutating and validating webhooks)
- Persists state changes to etcd (the ONLY component that writes to etcd)
- Watches for resource changes and streams updates to clients

**Request pipeline:**
```
kubectl apply -f deployment.yaml
         |
         v
   [Authentication]  ← Verify identity (client cert, token, etc.)
         |
         v
   [Authorization]   ← RBAC: Does user have permission?
         |
         v
[Admission Controllers] ← Mutating + Validating webhooks
         |
         v
    [Validation]     ← Schema validation
         |
         v
    [etcd Write]     ← Persist to distributed key-value store
         |
         v
    [Watch Streams]  ← Notify controllers/clients
```

**Why it's needed:**
- Centralized entry point enforces consistent authentication and authorization
- Decouples clients from etcd (etcd is not designed for direct client access)
- Provides versioning, validation, and extensibility (custom resources)

**What happens if it fails:**
- kubectl commands fail
- Existing workloads continue running (kubelet caches pod specs)
- Controllers cannot react to changes (no new pods, services, etc.)
- **Recovery:** API server is stateless; restart or failover to another replica

**High Availability:**
Run multiple API server replicas behind a load balancer. Each replica is stateless and can serve requests independently.

---

### etcd

**What it does:**
etcd is a distributed key-value store that holds ALL cluster state. Every resource you create (pods, services, deployments, secrets) is stored here. Think of it as Kubernetes' database.

**Key characteristics:**
- Distributed consensus via **Raft protocol** (leader election + log replication)
- Strongly consistent reads (linearizable)
- Watch API for real-time change notifications
- Stores data as key-value pairs (e.g., `/registry/pods/default/my-pod`)

**What's stored in etcd:**
- Pod definitions
- Service endpoints
- Secrets and ConfigMaps
- RBAC policies
- Node status
- Custom resources

**Example etcd key structure:**
```
/registry/
  ├── pods/
  │   ├── default/
  │   │   ├── doctor-backend-7d8f9-abc12
  │   │   └── doctor-frontend-6c5e8-def34
  │   └── kube-system/
  │       └── coredns-5d78c-ghi56
  ├── services/
  │   └── default/
  │       ├── doctor-backend
  │       └── doctor-frontend
  └── secrets/
      └── default/
          └── postgres-credentials
```

**Why it's needed:**
- Single source of truth for cluster state
- Provides watch mechanism for controllers to react to changes
- Survives node failures via replication

**What happens if it fails:**
- If the leader fails, Raft elects a new leader (typically <1 second downtime)
- If quorum is lost (e.g., 2/3 nodes fail), cluster becomes read-only
- If ALL etcd nodes fail and backups are lost, cluster state is GONE (catastrophic)

**Raft consensus basics:**
- 3 or 5 node cluster (odd numbers for quorum)
- Leader handles all writes, replicates to followers
- Quorum = (n/2) + 1 (e.g., 2/3 nodes for 3-node cluster)

**Backup importance:**
```bash
# Take etcd snapshot
ETCDCTL_API=3 etcdctl snapshot save snapshot.db \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key

# Restore from snapshot (disaster recovery)
ETCDCTL_API=3 etcdctl snapshot restore snapshot.db \
  --data-dir=/var/lib/etcd-restore
```

**In GKE Autopilot:**
Google manages etcd (automatic backups, HA configuration). You don't access it directly.

---

### Scheduler (kube-scheduler)

**What it does:**
The scheduler watches for newly created pods that have no `nodeName` assigned and selects the best node for each pod to run on.

**Scheduling algorithm (2 phases):**

**Phase 1: Filtering**
Eliminate nodes that don't meet pod requirements:
- Insufficient CPU/memory (based on pod requests)
- Taints don't match pod tolerations
- Node selector/affinity rules violated
- Volume conflicts (e.g., pod needs a volume already mounted elsewhere)

**Phase 2: Scoring**
Rank remaining nodes based on:
- Resource balance (prefer nodes with balanced CPU/memory usage)
- Inter-pod affinity/anti-affinity
- Topology spread constraints
- User-defined priorities

**Example:**
```yaml
# Pod with resource requests and node affinity
apiVersion: v1
kind: Pod
metadata:
  name: doctor-backend
spec:
  containers:
  - name: backend
    image: gcr.io/project/doctor-backend:v1
    resources:
      requests:
        cpu: 500m      # Scheduler filters nodes with <500m available
        memory: 512Mi
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: workload-type
            operator: In
            values:
            - backend
```

**Why it's needed:**
- Automates placement decisions (manual assignment doesn't scale)
- Optimizes cluster resource utilization
- Enforces constraints (affinity, taints, topology)

**What happens if it fails:**
- New pods remain in `Pending` state (no node assignment)
- Existing pods continue running unaffected
- **Recovery:** Scheduler is stateless; restart it, and it resumes scheduling pending pods

---

### Controller Manager (kube-controller-manager)

**What it does:**
Bundles multiple controllers into a single binary. Each controller runs an independent reconciliation loop, watching for changes and driving current state toward desired state.

**Key controllers:**

**Deployment Controller:**
- Watches Deployment resources
- Creates/updates ReplicaSets to match desired state
- Handles rollouts and rollbacks

**ReplicaSet Controller:**
- Watches ReplicaSet resources
- Creates/deletes pods to maintain desired replica count

**Node Controller:**
- Monitors node health (heartbeats via kubelet)
- Marks nodes as NotReady if heartbeats stop
- Evicts pods from unhealthy nodes

**Job Controller:**
- Manages Job resources (run-to-completion pods)
- Tracks completions and failures
- Cleans up completed pods

**Endpoint Controller:**
- Watches Services and Pods
- Populates Endpoints objects (IP addresses of healthy pods backing a service)

**Service Account Controller:**
- Creates default ServiceAccounts for namespaces
- Generates tokens for authentication

**Reconciliation loop pattern (pseudocode):**
```python
while True:
    desired = get_desired_state_from_etcd()
    current = get_current_state_from_cluster()

    if current != desired:
        take_action_to_reconcile(current, desired)

    sleep_until_next_change_or_timeout()
```

**Why it's needed:**
- Automates cluster management (manual scaling doesn't work at scale)
- Self-healing (replace failed pods, reschedule workloads)
- Declarative infrastructure (specify what you want, not how to get there)

**What happens if it fails:**
- Existing resources continue running
- No automatic reconciliation (e.g., failed pods not replaced)
- **Recovery:** Controller manager is stateless; restart it, and it resumes reconciliation

---

## Control Plane Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CONTROL PLANE                             │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                      API Server                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │  RESTful API (HTTPS)                             │   │   │
│  │  │  - Authentication (certs, tokens, OIDC)          │   │   │
│  │  │  - Authorization (RBAC)                          │   │   │
│  │  │  - Admission Controllers (mutating/validating)   │   │   │
│  │  │  - Schema Validation                             │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  │                           │                               │   │
│  │                           │ (ONLY component that          │   │
│  │                           │  writes to etcd)              │   │
│  │                           ▼                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              │                                   │
│  ┌───────────────────────────┴──────────────────────────────┐  │
│  │                         etcd                              │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  Distributed Key-Value Store                       │  │  │
│  │  │  - Raft consensus (leader + followers)            │  │  │
│  │  │  - Stores ALL cluster state                       │  │  │
│  │  │  - Watch API for change notifications             │  │  │
│  │  │  /registry/pods/, /registry/services/, ...        │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ▲                                   │
│                              │ (watches for changes)             │
│                              │                                   │
│  ┌───────────────────────────┴──────────────────────────────┐  │
│  │                      Scheduler                            │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  - Watches for unscheduled pods                    │  │  │
│  │  │  - Filtering phase (node selection)                │  │  │
│  │  │  - Scoring phase (ranking)                         │  │  │
│  │  │  - Assigns pod.spec.nodeName                       │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ▲                                   │
│                              │ (watches for changes)             │
│                              │                                   │
│  ┌───────────────────────────┴──────────────────────────────┐  │
│  │                  Controller Manager                       │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  Deployment Controller  ──┐                        │  │  │
│  │  │  ReplicaSet Controller  ──┤                        │  │  │
│  │  │  Node Controller        ──┤ Reconciliation Loops   │  │  │
│  │  │  Job Controller         ──┤ (watch → compare →     │  │  │
│  │  │  Endpoint Controller    ──┤  reconcile)            │  │  │
│  │  │  ServiceAccount Ctrl    ──┘                        │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ (API calls to node components)
                              ▼
                     ┌─────────────────┐
                     │   Worker Nodes  │
                     │  (kubelet, etc) │
                     └─────────────────┘
```

**Key interactions:**
1. kubectl → API Server (HTTP/HTTPS)
2. API Server ↔ etcd (gRPC, only component with direct etcd access)
3. Scheduler → API Server (watch for pods, update pod.spec.nodeName)
4. Controller Manager → API Server (watch for resources, create/update/delete)
5. API Server → kubelet (trigger pod actions on nodes)

---

## Node Components

Worker nodes run application workloads (pods). Each node has three core components:

### kubelet

**What it does:**
The kubelet is an agent running on every node. It's responsible for starting containers, monitoring their health, and reporting status back to the API server.

**Key responsibilities:**
- Watches the API server for pods assigned to its node (via pod.spec.nodeName)
- Instructs the container runtime to start/stop containers
- Executes liveness/readiness/startup probes
- Reports node and pod status to the API server
- Mounts volumes (ConfigMaps, Secrets, PersistentVolumes)

**How it gets pod specs:**
- Primary: Watches API server for pods with matching nodeName
- Fallback: Reads static pod manifests from `/etc/kubernetes/manifests/` (used for control plane components)

**Probe execution example:**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: doctor-backend
spec:
  containers:
  - name: backend
    image: gcr.io/project/doctor-backend:v1
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

kubelet executes HTTP GET requests to the specified endpoints every 10/5 seconds. If probes fail, it restarts the container (liveness) or removes it from service endpoints (readiness).

**Why it's needed:**
- Bridge between Kubernetes control plane and container runtime
- Local enforcement of pod lifecycle policies
- Health monitoring without overloading the API server

**What happens if it fails:**
- Node marked as NotReady by the node controller
- No new pods scheduled to the node
- Existing pods continue running (but no health checks)
- After grace period, pods are evicted and rescheduled elsewhere

---

### kube-proxy

**What it does:**
kube-proxy implements Kubernetes Services by managing network rules on each node. It ensures that traffic sent to a Service's ClusterIP gets routed to one of the healthy backing pods.

**How it works (iptables mode):**
- Watches the API server for Service and Endpoint changes
- Configures iptables rules to implement load balancing
- Traffic to ClusterIP → DNAT to pod IP

**Example iptables rules (simplified):**
```bash
# Service: doctor-backend ClusterIP 10.96.100.200:8000
# Backing pods: 10.244.1.10:8000, 10.244.2.15:8000

-A KUBE-SERVICES -d 10.96.100.200/32 -p tcp --dport 8000 \
  -j KUBE-SVC-DOCTOR-BACKEND

-A KUBE-SVC-DOCTOR-BACKEND -m statistic --mode random --probability 0.5 \
  -j KUBE-SEP-POD1  # 50% to pod 1

-A KUBE-SVC-DOCTOR-BACKEND \
  -j KUBE-SEP-POD2  # 50% to pod 2

-A KUBE-SEP-POD1 -p tcp -j DNAT --to-destination 10.244.1.10:8000
-A KUBE-SEP-POD2 -p tcp -j DNAT --to-destination 10.244.2.15:8000
```

**Alternative modes:**
- **IPVS:** More efficient than iptables for large clusters (hash-based load balancing)
- **userspace:** Legacy mode (not recommended)

**Why it's needed:**
- Decouples service discovery from pod IPs (pods are ephemeral, services are stable)
- Load balances traffic across multiple pod replicas
- Enables cluster-wide service networking

**What happens if it fails:**
- Existing connections may continue (iptables rules persist)
- New services/endpoints not reflected in iptables rules
- Service discovery breaks for new pods
- **Recovery:** kube-proxy is stateless; restart it, and it reprograms iptables

---

### Container Runtime

**What it does:**
The container runtime is responsible for pulling images and running containers. Kubernetes communicates with the runtime via the Container Runtime Interface (CRI).

**Common runtimes:**
- **containerd:** Most popular (lightweight, CNCF graduated project)
- **CRI-O:** Red Hat-backed, OCI-compliant
- **Docker Engine:** Removed in Kubernetes 1.24 (see below)

**Why Docker removal didn't matter:**
Docker Engine is NOT a CRI-compatible runtime. Kubernetes used a shim called `dockershim` to translate CRI calls to Docker API calls. When dockershim was removed in K8s 1.24:
- Docker images still work (OCI image spec is standard)
- Docker CLI still works on developer machines
- Kubernetes now talks directly to containerd (which Docker Engine uses internally)

**CRI interface example:**
```go
// Kubernetes API call
kubelet.CreateContainer(pod, containerConfig)
         |
         v
    [CRI Plugin]
         |
         v
  containerd.Pull(image)
  containerd.Create(container)
  containerd.Start(container)
```

**Why it's needed:**
- Abstracts container lifecycle management
- Enables runtime choice (containerd, CRI-O, etc.)
- Isolates Kubernetes from OCI spec changes

---

## Node Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          WORKER NODE                             │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                       kubelet                            │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │  - Watches API server for pods (nodeName match) │   │   │
│  │  │  - Instructs container runtime (via CRI)        │   │   │
│  │  │  - Executes probes (liveness/readiness)         │   │   │
│  │  │  - Mounts volumes (ConfigMaps, Secrets, PVs)    │   │   │
│  │  │  - Reports pod/node status to API server        │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              │ (CRI calls)                       │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Container Runtime                       │   │
│  │                    (containerd)                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │  - Pull images from registry                    │   │   │
│  │  │  - Create/start/stop containers                 │   │   │
│  │  │  - Monitor container lifecycle                  │   │   │
│  │  │  - Manage container namespaces/cgroups          │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              │ (spawns containers)               │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                        Pods                              │   │
│  │  ┌──────────────────┐  ┌──────────────────┐             │   │
│  │  │  doctor-backend  │  │ doctor-frontend  │             │   │
│  │  │  ┌────────────┐  │  │  ┌────────────┐  │             │   │
│  │  │  │ Container  │  │  │  │ Container  │  │             │   │
│  │  │  │ (FastAPI)  │  │  │  │ (React)    │  │             │   │
│  │  │  └────────────┘  │  │  └────────────┘  │             │   │
│  │  │  IP: 10.244.1.10 │  │  IP: 10.244.1.11 │             │   │
│  │  └──────────────────┘  └──────────────────┘             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     kube-proxy                           │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │  - Watches API server for Services/Endpoints    │   │   │
│  │  │  - Programs iptables/IPVS rules                 │   │   │
│  │  │  - ClusterIP → pod IP DNAT                      │   │   │
│  │  │  - Load balances across healthy pods            │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              │ (iptables rules)                  │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Network Stack                          │   │
│  │  - iptables NAT rules                                    │   │
│  │  - Routing tables                                        │   │
│  │  - CNI plugin (Calico/Cilium/Flannel)                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ (pod-to-pod traffic)
                              ▼
                     ┌─────────────────┐
                     │   Other Nodes   │
                     └─────────────────┘
```

**Key interactions:**
1. kubelet → API Server (watch for pods, report status)
2. kubelet → Container Runtime (CRI calls: pull image, start container)
3. Container Runtime → Pods (spawn containers)
4. kube-proxy → API Server (watch for services/endpoints)
5. kube-proxy → iptables (program NAT rules for service load balancing)
6. Pods → Network Stack → Other Pods (via CNI plugin)

---

## Request Flow: kubectl apply to Running Container

Let's trace the full journey of a deployment from your terminal to a running container.

**Command:**
```bash
kubectl apply -f deployment.yaml
```

**YAML manifest:**
```yaml
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
      - name: backend
        image: gcr.io/project/doctor-backend:v1.2.0
        ports:
        - containerPort: 8000
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
```

### Step-by-Step Trace

**Step 1: kubectl reads YAML and sends HTTP POST**
```
kubectl → API Server
POST /apis/apps/v1/namespaces/doctor-app/deployments
Content-Type: application/json
Authorization: Bearer <token>

{
  "apiVersion": "apps/v1",
  "kind": "Deployment",
  "metadata": {"name": "doctor-backend", ...},
  ...
}
```

**Step 2: API Server authenticates the request**
- Validates bearer token or client certificate
- Maps token to user identity (e.g., ServiceAccount or OIDC user)

**Step 3: API Server authorizes the request (RBAC)**
- Checks if user has permission to create Deployments in `doctor-app` namespace
- RBAC policy example:
  ```yaml
  apiVersion: rbac.authorization.k8s.io/v1
  kind: RoleBinding
  metadata:
    name: deployer
    namespace: doctor-app
  subjects:
  - kind: User
    name: alice
  roleRef:
    kind: Role
    name: deployment-creator
    apiGroup: rbac.authorization.k8s.io

  ---
  apiVersion: rbac.authorization.k8s.io/v1
  kind: Role
  metadata:
    name: deployment-creator
    namespace: doctor-app
  rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["create", "update", "get", "list"]
  ```

**Step 4: Admission controllers run**
- **Mutating admission controllers** (run first, can modify the request):
  - Add default values (e.g., imagePullPolicy: IfNotPresent)
  - Inject sidecars (e.g., Istio proxy)
- **Validating admission controllers** (run second, can reject the request):
  - Enforce organizational policies (e.g., require resource limits)
  - Check quotas (e.g., namespace CPU/memory limits)

**Step 5: API Server validates the schema**
- Ensures required fields are present
- Validates field types (e.g., replicas is an integer)
- Checks against OpenAPI spec

**Step 6: API Server writes to etcd**
```
etcdctl put /registry/deployments/doctor-app/doctor-backend <JSON>
```

**Step 7: Deployment controller creates ReplicaSet**
The Deployment controller watches for new/updated Deployments:
```
Deployment controller:
  - Sees new Deployment: doctor-backend (3 replicas)
  - Creates ReplicaSet: doctor-backend-7d8f9 (3 replicas)
  - Writes ReplicaSet to API Server → etcd
```

**Step 8: ReplicaSet controller creates Pod objects**
The ReplicaSet controller watches for new/updated ReplicaSets:
```
ReplicaSet controller:
  - Sees new ReplicaSet: doctor-backend-7d8f9 (3 replicas)
  - Creates 3 Pod objects: doctor-backend-7d8f9-abc12, -def34, -ghi56
  - Writes Pods to API Server → etcd (without nodeName)
```

**Step 9: Scheduler assigns pods to nodes**
The scheduler watches for unscheduled pods (pods without nodeName):
```
Scheduler:
  - Sees 3 unscheduled pods
  - Filtering: Eliminate nodes with insufficient CPU/memory
  - Scoring: Rank remaining nodes (balance, affinity, etc.)
  - Assigns:
      doctor-backend-7d8f9-abc12 → node-1
      doctor-backend-7d8f9-def34 → node-2
      doctor-backend-7d8f9-ghi56 → node-1
  - Updates pod.spec.nodeName via API Server → etcd
```

**Step 10: kubelet starts containers**
kubelet on each node watches for pods with matching nodeName:
```
kubelet on node-1:
  - Sees 2 pods assigned: doctor-backend-7d8f9-abc12, -ghi56
  - Calls CRI: PullImage(gcr.io/project/doctor-backend:v1.2.0)
  - Calls CRI: CreateContainer(pod-abc12, containerConfig)
  - Calls CRI: StartContainer(pod-abc12)
  - Repeat for pod-ghi56
  - Reports pod status (Running) to API Server

kubelet on node-2:
  - Sees 1 pod assigned: doctor-backend-7d8f9-def34
  - Pulls image, creates, starts container
  - Reports pod status (Running) to API Server
```

### Sequence Diagram (ASCII)

```
kubectl          API Server      etcd       Deployment      ReplicaSet      Scheduler       kubelet
  |                  |             |         Controller      Controller         |              |
  |-- POST deploy -->|             |              |              |              |              |
  |                  |             |              |              |              |              |
  |                  |-- Auth ----->              |              |              |              |
  |                  |-- RBAC ----->              |              |              |              |
  |                  |-- Admit ---->              |              |              |              |
  |                  |             |              |              |              |              |
  |                  |-- Write ---->              |              |              |              |
  |                  |             |              |              |              |              |
  |                  |             |              |              |              |              |
  |                  |<----------- Watch Deployment ------------>|              |              |
  |                  |             |              |              |              |              |
  |                  |<- Create ReplicaSet -------|              |              |              |
  |                  |-- Write ---->              |              |              |              |
  |                  |             |              |              |              |              |
  |                  |             |              |<----------- Watch RS ------>|              |
  |                  |             |              |              |              |              |
  |                  |<--------- Create 3 Pods ------------------|              |              |
  |                  |-- Write ---->              |              |              |              |
  |                  |             |              |              |              |              |
  |                  |             |              |              |<-- Watch unscheduled pods --|
  |                  |             |              |              |              |              |
  |                  |<----------------------- Assign nodeName --|              |              |
  |                  |-- Write ---->              |              |              |              |
  |                  |             |              |              |              |              |
  |                  |             |              |              |              |<-- Watch pods (nodeName match)
  |                  |             |              |              |              |              |
  |                  |             |              |              |              |<- Pull image-|
  |                  |             |              |              |              |<- Create -----|
  |                  |             |              |              |              |<- Start ------|
  |                  |             |              |              |              |              |
  |                  |<---------------------- Report status (Running) ----------|              |
  |                  |-- Write ---->              |              |              |              |
  |                  |             |              |              |              |              |
  |<- 200 OK --------|             |              |              |              |              |
```

**Time breakdown (typical):**
- Step 1-6 (kubectl → etcd): <100ms
- Step 7-8 (controllers create ReplicaSet/Pods): 100-200ms
- Step 9 (scheduler assigns nodes): 50-200ms
- Step 10 (kubelet pulls image and starts container): 1-10 seconds (depends on image size)

**Total latency from kubectl apply to running container:** 2-15 seconds.

---

## Kubernetes Networking Model

Kubernetes enforces a flat network model where every pod can communicate with every other pod without NAT. This simplifies application networking and enables microservices to discover each other easily.

### Core Requirements

**1. Every pod gets its own IP address**
- No port mapping required (unlike Docker's `-p 8080:80`)
- Each pod has a unique IP in the cluster's pod CIDR range

**2. Pods can communicate with all other pods without NAT**
- Pod-to-pod traffic flows directly using pod IPs
- No address translation between pods (even across nodes)

**3. Nodes can communicate with all pods without NAT**
- Nodes use pod IPs to reach containers (e.g., kubelet health checks)

**4. A pod's IP address is the same inside and outside the pod**
- No confusion about "internal" vs "external" IPs

### How It Works: CNI Plugins

Kubernetes delegates network setup to **Container Network Interface (CNI)** plugins. When a pod is created, kubelet calls the CNI plugin to:
1. Allocate an IP address from the pod CIDR
2. Create network interfaces in the pod's namespace
3. Configure routing tables to enable pod-to-pod communication

**Popular CNI plugins:**

**Calico:**
- Layer 3 networking (pure IP routing, no overlay)
- Uses BGP to propagate routes between nodes
- Advanced network policies (default deny, egress rules)
- Good for large clusters

**Cilium:**
- eBPF-based (programmable kernel networking)
- High performance, low latency
- Layer 7 network policies (HTTP-aware)
- Observability features (Hubble)

**Flannel:**
- Simple overlay network (VXLAN by default)
- Easy to set up, minimal configuration
- Good for small clusters

**Weave Net:**
- Encrypted overlay network
- Automatic mesh networking
- Good for multi-cloud deployments

### GKE VPC-Native Networking

In **GKE Autopilot**, pods receive IPs from the VPC subnet (not an overlay network). This enables:
- **Direct routing from VPC:** VMs, Cloud Functions, and other GCP services can reach pod IPs without NAT
- **Network policies:** GKE uses Calico or Cilium for firewall rules
- **Alias IP ranges:** Efficient IP allocation (secondary CIDR ranges on node subnets)

**Example GKE cluster configuration:**
```bash
gcloud container clusters create doctor-cluster \
  --enable-ip-alias \
  --cluster-ipv4-cidr=/14 \      # Pod CIDR (65k IPs)
  --services-ipv4-cidr=/20 \     # Service CIDR (4k IPs)
  --enable-autopilot
```

**Pod IP assignment:**
```
Node 1: 10.244.0.0/24 → Pods: 10.244.0.1 - 10.244.0.254
Node 2: 10.244.1.0/24 → Pods: 10.244.1.1 - 10.244.1.254
Node 3: 10.244.2.0/24 → Pods: 10.244.2.1 - 10.244.2.254
```

### Network Policy Example

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-policy
  namespace: doctor-app
spec:
  podSelector:
    matchLabels:
      app: doctor-backend
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: doctor-frontend
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
```

This policy:
- **Ingress:** Only allow traffic from frontend pods on port 8000
- **Egress:** Only allow traffic to postgres pods on port 5432
- **Default:** Deny all other traffic (implicit deny-all when policy exists)

---

## DNS in Kubernetes

Kubernetes provides cluster-internal DNS via **CoreDNS** (previously kube-dns). This enables pods to discover services by name rather than hardcoding IP addresses.

### CoreDNS Architecture

CoreDNS runs as a Deployment in the `kube-system` namespace:
```bash
kubectl get pods -n kube-system -l k8s-app=kube-dns

NAME                       READY   STATUS
coredns-5d78c9b9d4-abc12   1/1     Running
coredns-5d78c9b9d4-def34   1/1     Running
```

Every pod is automatically configured to use CoreDNS as its DNS resolver:
```bash
# Inside a pod
cat /etc/resolv.conf

nameserver 10.96.0.10        # ClusterIP of kube-dns Service
search doctor-app.svc.cluster.local svc.cluster.local cluster.local
options ndots:5
```

### Service DNS Names

Services receive DNS A/AAAA records in the format:
```
<service>.<namespace>.svc.cluster.local
```

**Example:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: doctor-backend
  namespace: doctor-app
spec:
  selector:
    app: doctor-backend
  ports:
  - port: 8000
    targetPort: 8000
```

DNS entries:
```
doctor-backend.doctor-app.svc.cluster.local  → 10.96.100.200 (ClusterIP)
doctor-backend.doctor-app.svc                → 10.96.100.200 (shorthand)
doctor-backend.doctor-app                    → 10.96.100.200 (shorthand)
doctor-backend                               → 10.96.100.200 (if in same namespace)
```

**Full DNS lookup flow:**
```
frontend pod → CoreDNS
  Query: doctor-backend

CoreDNS:
  - Searches: doctor-backend.doctor-app.svc.cluster.local (match!)
  - Returns: 10.96.100.200 (Service ClusterIP)

frontend pod → kube-proxy (iptables rules)
  - DNAT: 10.96.100.200:8000 → 10.244.1.10:8000 (backend pod)

frontend pod → backend pod
  - HTTP GET http://10.244.1.10:8000/api/patients
```

### Headless Services (Pod IP Discovery)

For direct pod-to-pod communication (e.g., StatefulSet databases), use a headless service:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: doctor-app
spec:
  clusterIP: None  # Headless service
  selector:
    app: postgres
  ports:
  - port: 5432
```

DNS returns pod IPs instead of ClusterIP:
```bash
nslookup postgres.doctor-app.svc.cluster.local

Server:  10.96.0.10
Address: 10.96.0.10#53

Name:    postgres.doctor-app.svc.cluster.local
Address: 10.244.1.20  # Pod 1
Address: 10.244.2.15  # Pod 2
```

### StatefulSet Pod DNS

StatefulSet pods get predictable DNS names:
```
<pod-name>.<service-name>.<namespace>.svc.cluster.local
```

**Example:**
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: doctor-app
spec:
  serviceName: postgres  # Headless service
  replicas: 3
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
```

DNS entries:
```
postgres-0.postgres.doctor-app.svc.cluster.local → 10.244.1.20
postgres-1.postgres.doctor-app.svc.cluster.local → 10.244.2.15
postgres-2.postgres.doctor-app.svc.cluster.local → 10.244.3.10
```

**Use case:** Direct connection to primary database:
```python
# In backend pod
DATABASE_URL = "postgresql://user:pass@postgres-0.postgres.doctor-app.svc.cluster.local:5432/doctor"
```

### External DNS (ExternalName Service)

To access external services (e.g., Cloud SQL) via Kubernetes DNS:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: doctor-app
spec:
  type: ExternalName
  externalName: postgres.us-central1.sql.gcp.cloud.google.com
```

Pods can now use `postgres.doctor-app.svc.cluster.local` to reach the external database.

---

## Recap and Key Takeaways

### Control Plane Components
- **API Server:** Front door to the cluster, handles authentication/authorization/admission, ONLY component that writes to etcd
- **etcd:** Distributed key-value store, single source of truth, Raft consensus for HA
- **Scheduler:** Assigns pods to nodes via filtering and scoring algorithm
- **Controller Manager:** Reconciliation loops that drive current state toward desired state

### Node Components
- **kubelet:** Agent that starts containers, executes probes, reports status
- **kube-proxy:** Implements Services via iptables/IPVS rules (ClusterIP → pod IP DNAT)
- **Container runtime:** containerd (CRI-compatible), pulls images and runs containers

### Request Flow (kubectl apply → running container)
1. kubectl → API Server (HTTP POST)
2. Authentication (verify identity)
3. Authorization (RBAC check)
4. Admission controllers (mutating + validating)
5. Schema validation
6. Write to etcd
7. Deployment controller creates ReplicaSet
8. ReplicaSet controller creates Pods
9. Scheduler assigns nodeName
10. kubelet pulls image and starts container

**Latency:** 2-15 seconds (mostly image pull time)

### Networking
- **Pod networking:** Every pod gets its own IP, no NAT between pods
- **CNI plugins:** Calico, Cilium, Flannel implement the network model
- **GKE VPC-native:** Pods receive VPC IPs (no overlay network)

### DNS
- **CoreDNS:** Cluster-internal DNS in kube-system namespace
- **Service DNS:** `<service>.<namespace>.svc.cluster.local` → ClusterIP
- **Headless services:** `clusterIP: None` returns pod IPs for direct communication
- **StatefulSet DNS:** `<pod-name>.<service>.<namespace>.svc.cluster.local` for stable identities

### Debugging Tips
- **Pod stuck in Pending:** Check scheduler logs, node resources, taints/tolerations
- **Service not working:** Verify kube-proxy logs, check iptables rules (`iptables -t nat -L`)
- **DNS resolution fails:** Check CoreDNS pods, verify /etc/resolv.conf in pod
- **etcd corruption:** Restore from snapshot (always maintain regular backups)

### Next Steps
- **Document 03:** Deploying the AI Doctor Assistant to Kubernetes (manifests, ConfigMaps, Secrets)
- **Document 04:** Ingress and Load Balancing (expose services externally)
- **Document 05:** Observability (logging, metrics, tracing)

---

**End of Document 02**
