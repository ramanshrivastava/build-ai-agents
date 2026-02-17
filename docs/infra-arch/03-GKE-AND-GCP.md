# 03 — Google Kubernetes Engine & GCP Services

**Series:** Kubernetes Educational Documentation for AI Doctor Assistant
**Document:** 03 of 11
**Focus:** GKE-specific features, Autopilot vs Standard, GCP service integration, pricing

---

## Overview

Google Kubernetes Engine (GKE) is Google Cloud Platform's managed Kubernetes offering. While it runs standard Kubernetes under the hood, GKE adds significant operational conveniences, security features, and tight integration with other GCP services. This document explains what GKE provides beyond vanilla Kubernetes, compares Autopilot and Standard modes, estimates costs for the AI Doctor Assistant, and provides a setup walkthrough.

---

## 1. What GKE Adds on Top of Vanilla Kubernetes

Running your own Kubernetes cluster (on bare metal or VMs) requires managing:
- Control plane components (API server, etcd, scheduler, controller manager)
- Node operating systems and security patches
- Networking plugins (CNI)
- Monitoring and logging infrastructure
- Certificate rotation and cluster upgrades

GKE eliminates most of this operational burden:

### Managed Control Plane

Google runs the Kubernetes control plane (API server, etcd, scheduler, controller manager) in their own infrastructure. You never SSH into control plane nodes or worry about etcd backups. GKE handles:
- High availability of the control plane (regional clusters get multi-zone API server)
- Automatic control plane upgrades
- Scaling the control plane as your cluster grows

### Auto-Upgrades and Auto-Repair

**Auto-upgrades:** GKE can automatically upgrade node pools to new Kubernetes versions during maintenance windows. You configure the maintenance window, GKE handles the rolling upgrade.

**Auto-repair:** If a node becomes unhealthy (fails health checks), GKE automatically recreates it. This prevents situations where a single failed node causes outages.

### Integrated Logging and Monitoring

GKE automatically ships logs and metrics to Google Cloud Operations (formerly Stackdriver):
- **Cloud Logging:** All pod stdout/stderr streams to Cloud Logging. Query with filters, set up alerts, export to BigQuery.
- **Cloud Monitoring:** Metrics for CPU, memory, disk, network at pod and node level. Pre-built dashboards for cluster health.

No need to deploy Prometheus, Grafana, Fluentd, or Elasticsearch yourself (though you can if you want).

### VPC-Native Networking

In GKE, pods get IP addresses from your VPC's IP range (called "alias IPs"). This means:
- Pods are routable within your VPC without NAT
- You can firewall pod traffic using VPC firewall rules
- Services can be accessed from other GCP resources (Cloud Functions, Compute Engine VMs) without exposing them publicly

Contrast with traditional Kubernetes where pod IPs are in a separate overlay network (flannel, Calico) and require NAT or additional networking configuration to reach from outside the cluster.

### Workload Identity

Workload Identity maps Kubernetes service accounts to Google Cloud IAM service accounts. This allows pods to authenticate to GCP services (Cloud Storage, Secret Manager, BigQuery) without embedding service account key files in your images or Secrets.

Example: Your backend pod needs to read from Secret Manager. With Workload Identity:
1. Create a GCP service account with Secret Manager Reader role
2. Bind it to a Kubernetes service account
3. Run your pod with that Kubernetes service account
4. Application code uses Application Default Credentials (no key file needed)

This is more secure than downloading a JSON key and mounting it as a Secret.

### Integrated Load Balancing

When you create a Service of type `LoadBalancer`, GKE provisions a Google Cloud Load Balancer (GCLB) automatically. When you create an Ingress, GKE provisions an HTTP(S) Load Balancer with SSL termination, URL routing, and global anycast IPs.

### Container-Optimized OS

GKE nodes run Container-Optimized OS (COS) by default — a minimal Linux distribution designed for running containers. Benefits:
- Smaller attack surface (fewer packages)
- Automatic security updates
- Read-only root filesystem
- Locked-down by default

You can also choose Ubuntu or Windows Server node images if needed.

### Security Features

- **Binary Authorization:** Enforce that only signed container images can run in your cluster
- **Vulnerability Scanning:** Artifact Registry automatically scans images for CVEs
- **Shielded GKE Nodes:** Nodes with secure boot and integrity monitoring
- **Private Clusters:** Nodes have no public IPs, control plane is accessible only via private endpoint

---

## 2. Autopilot vs Standard — Detailed Comparison

GKE offers two modes:

### Comparison Table

| Aspect | Autopilot | Standard |
|--------|-----------|----------|
| **Control plane management** | Google manages | Google manages |
| **Node management** | Google manages nodes (you never see VMs) | You create and manage node pools |
| **Billing model** | Pay per pod resource (vCPU, memory, ephemeral storage) | Pay per node VM (even if pods are idle) |
| **Minimum cost** | ~$0 for empty cluster (no pods = no cost, except PVCs) | Always paying for at least 1 node VM |
| **Pod resource defaults** | Requests required; defaults applied if missing | Requests optional |
| **GPU support** | Yes (NVIDIA T4, A100, L4) | Yes (more VM types available) |
| **Node SSH access** | No (nodes are abstracted away) | Yes (can SSH to nodes) |
| **DaemonSets** | Allowed (Google manages resource allocation) | Allowed |
| **Privileged pods** | Not allowed | Allowed |
| **Node pools** | Google decides node types and scales automatically | You configure node pools (machine type, disk, zones) |
| **Scaling** | Automatic based on pod resource requests | You configure autoscaling per node pool |
| **Best for** | Workloads with variable load, dev/test, cost optimization | Workloads needing privileged containers, specific node types, or full node control |
| **Constraints** | No host networking, no privileged containers, no hostPath volumes, no node affinity | None (full Kubernetes flexibility) |

### Autopilot Deep Dive

**How billing works:**
- You specify CPU, memory, and ephemeral storage requests in your pod spec
- GKE provisions VMs to fit your pods (you never see these VMs)
- You pay only for the resources requested by running pods
- Pricing: ~$0.05/vCPU-hour, ~$0.0056/GB-memory-hour (varies by region)

**Resource requests required:**
If you don't specify requests, Autopilot applies defaults:
- CPU: 500m (0.5 vCPU) per container
- Memory: 2Gi per container
- Ephemeral storage: 1Gi per pod

This can be expensive if you have many small containers. Always set explicit requests.

**Constraints:**
- No privileged containers (security isolation)
- No host networking (pods must use pod network)
- No hostPath volumes (use ConfigMaps, Secrets, or PVCs instead)
- No node affinity/taints (Google decides node placement)

**Why these constraints?**
Google needs to bin-pack your pods efficiently across shared infrastructure. Allowing privileged containers or host networking would break multi-tenancy.

**Free tier:**
- 1 zonal Autopilot cluster has no cluster management fee
- Regional Autopilot clusters have a small management fee (~$0.10/hr = $73/mo)

### Standard Deep Dive

**How billing works:**
- You create node pools with specific VM machine types (e2-small, n1-standard-2, etc.)
- You pay for the VM per second, regardless of pod utilization
- Cluster management fee: $0.10/hr ($73/mo) for regional clusters, free for zonal clusters

**Node pools:**
A node pool is a group of nodes with the same configuration:
- Machine type (e.g., e2-medium = 2 vCPU, 4GB RAM)
- Disk size and type
- Zone(s)
- Autoscaling settings (min/max nodes)

You can have multiple node pools in one cluster (e.g., one pool for CPU workloads, one pool with GPUs).

**When to use Standard:**
- Need privileged containers (e.g., running Docker-in-Docker for CI/CD)
- Need specific node types (e.g., high-memory VMs)
- Want full control over node configuration
- Running production workloads where you know the baseline load

**Cost optimization:**
- Use Spot VMs (preemptible): 60-91% discount, but can be terminated with 30s notice
- Use e2-small or e2-micro for dev clusters
- Use cluster autoscaler to scale node count based on pending pods

---

## 3. Pricing Estimates for AI Doctor Assistant

### Application Resource Profile

| Component | Replicas | CPU Request | Memory Request | Persistent Storage |
|-----------|----------|-------------|----------------|-------------------|
| Frontend (Nginx serving React build) | 2 | 0.25 vCPU | 256Mi | None (ephemeral) |
| Backend (FastAPI + uvicorn) | 2 | 0.5 vCPU | 512Mi | None (ephemeral) |
| PostgreSQL | 1 | 0.5 vCPU | 1Gi | 10Gi SSD PVC |

**Why these resource requests?**
- Frontend: Nginx is lightweight, mostly serving static files
- Backend: Python + FastAPI has moderate overhead; 512Mi handles typical request load
- PostgreSQL: 1Gi memory allows reasonable buffer cache; 10Gi disk stores patient records, flags, briefings

### Autopilot Monthly Cost Estimate

**Region:** us-central1 (Iowa)
**Pricing (as of January 2025):**
- vCPU: $0.04980/hr = ~$36/mo per vCPU
- Memory: $0.00549/GB-hr = ~$4/mo per GB
- Ephemeral storage: $0.000165/GB-hr = ~$0.12/mo per GB (usually negligible)
- SSD persistent disk: $0.17/GB/mo
- Cluster management: $0 (zonal Autopilot)
- Ingress/Load Balancer: $18/mo (base rate) + $0.008/GB egress

**Calculation:**

**Frontend pods (2 replicas):**
- vCPU: 2 × 0.25 × $36 = $18/mo
- Memory: 2 × 0.25GB × $4 = $2/mo

**Backend pods (2 replicas):**
- vCPU: 2 × 0.5 × $36 = $36/mo
- Memory: 2 × 0.5GB × $4 = $4/mo

**PostgreSQL pod (1 replica):**
- vCPU: 1 × 0.5 × $36 = $18/mo
- Memory: 1 × 1GB × $4 = $4/mo
- PVC: 10GB × $0.17 = $1.70/mo

**Ingress/Load Balancer:**
- Base: $18/mo
- Egress: assume 5GB/mo = $0.04/mo (negligible)

**Total Autopilot estimate: $101.74/mo**

**Notes:**
- This assumes pods run 24/7. If you scale to 0 during off-hours, cost drops proportionally.
- Egress cost is low for development (most traffic is you accessing the app).
- No data transfer costs between pods (in-cluster traffic is free).

### Standard Monthly Cost Estimate (Zonal Cluster)

**Scenario:** 1 zonal cluster in us-central1, 1 e2-medium node

**Pricing:**
- e2-medium (2 vCPU, 4GB RAM): $0.03344/hr = $24.27/mo
- Cluster management: $0 (zonal cluster is free)
- SSD persistent disk: $0.17/GB/mo
- Ingress/Load Balancer: $18/mo base

**Calculation:**

**Node cost:** $24.27/mo

**Storage:** 10GB SSD PVC = $1.70/mo

**Load Balancer:** $18/mo

**Total Standard estimate: $43.97/mo**

**Why is Standard cheaper here?**
Because Autopilot charges per resource request, and our total requests (2 vCPU, 2.25GB RAM) fit within a single e2-medium node. If we scaled up to 10 pods, Autopilot would scale gracefully while Standard would require adding more nodes (jumping to $48+ for a second e2-medium).

### Standard with Regional Cluster (for HA)

**Scenario:** Regional cluster (3 zones), 1 e2-medium node per zone

**Calculation:**
- Nodes: 3 × $24.27 = $72.81/mo
- Cluster management: $0.10/hr = $72/mo (regional Standard cluster)
- Storage: $1.70/mo
- Load Balancer: $18/mo

**Total: $164.51/mo**

Regional clusters provide HA but are expensive for small workloads.

### Cost Comparison Table

| Component | Autopilot (Zonal) | Standard (Zonal) | Standard (Regional) |
|-----------|-------------------|------------------|---------------------|
| Frontend pods (2) | $20/mo | Included | Included |
| Backend pods (2) | $40/mo | Included | Included |
| PostgreSQL pod (1) | $22/mo | Included | Included |
| Node VMs | $0 (abstracted) | $24.27/mo | $72.81/mo |
| Cluster management | $0 | $0 | $72/mo |
| Persistent disk (10GB) | $1.70/mo | $1.70/mo | $1.70/mo |
| Load Balancer | $18/mo | $18/mo | $18/mo |
| **Total** | **~$102/mo** | **~$44/mo** | **~$165/mo** |

### Free Tier and Credits

**GCP free trial:**
- $300 credit for new accounts (valid for 90 days)
- Covers initial experimentation

**Always Free tier:**
- 1 non-preemptible e2-micro VM instance per month (us-west1, us-central1, us-east1)
- Doesn't cover Kubernetes node surcharges, so not practical for GKE

**Recommendation for AI Doctor Assistant:**
Use Autopilot for dev/staging (pay only when testing), switch to Standard zonal cluster for production if load is predictable.

---

## 4. GCP Services Relevant to Kubernetes

### Artifact Registry

**What it is:**
Managed container registry for Docker images, Helm charts, and other artifacts. Replaces the older Container Registry (gcr.io).

**How AI Doctor uses it:**
Store `backend:latest` and `frontend:latest` Docker images after building locally or in CI/CD.

**Pricing:**
- Storage: $0.10/GB/month
- Egress: $0.12/GB (within GCP) to $0.23/GB (internet)
- Typical cost for AI Doctor: ~$0.50/mo (images are <1GB combined)

**Repository naming:**
- Format: `REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE_NAME:TAG`
- Example: `us-central1-docker.pkg.dev/ai-doctor-prod/doctor-app/backend:v1.2.0`

**Why not Docker Hub?**
Artifact Registry is in the same GCP region as your GKE cluster, so image pulls are faster and free (no egress cost).

### Secret Manager

**What it is:**
Managed service for storing sensitive data: API keys, database passwords, TLS certificates.

**How AI Doctor uses it:**
Store `ANTHROPIC_API_KEY`, PostgreSQL `POSTGRES_PASSWORD`. Instead of creating Kubernetes Secrets manually, use External Secrets Operator to sync from Secret Manager to K8s Secrets.

**Pricing:**
- $0.06 per 10,000 access operations
- Typical cost: <$1/mo for small apps

**Advantages over K8s Secrets:**
- Secrets are encrypted at rest in Secret Manager (K8s Secrets are base64-encoded, not encrypted by default)
- Audit logs for secret access
- Centralized secret management across GCP services

**Example flow:**
1. Store API key in Secret Manager: `gcloud secrets create anthropic-api-key --data-file=key.txt`
2. Grant GKE service account read access: `gcloud secrets add-iam-policy-binding ...`
3. Use External Secrets Operator to create K8s Secret from Secret Manager secret

### Cloud SQL

**What it is:**
Managed PostgreSQL, MySQL, SQL Server. Google handles backups, replication, patching, high availability.

**Why AI Doctor is NOT using it initially:**
- Minimum cost: $7/mo for db-f1-micro (shared CPU, 0.6GB RAM) in us-central1
- Realistic cost for decent performance: $25-50/mo (db-g1-small with 1.7GB RAM)
- We're using in-cluster PostgreSQL to minimize cost during development

**When to migrate to Cloud SQL:**
- Production workloads requiring high availability (automatic failover)
- Need for automated backups with point-in-time recovery
- Compliance requirements (Cloud SQL has certifications like HIPAA, SOC 2)
- Want to offload database management entirely

**Cloud SQL Proxy:**
Cloud SQL doesn't expose a public IP by default. You connect via Cloud SQL Proxy (a sidecar container in your pod) that handles authentication and encryption.

### IAM & Workload Identity

**IAM (Identity and Access Management):**
Google Cloud's RBAC system. Defines who (identity) can do what (role) on which resource.

**Workload Identity:**
Bridges Kubernetes service accounts and GCP IAM service accounts.

**Without Workload Identity:**
To let a pod access GCP services, you'd:
1. Create a GCP service account
2. Download its JSON key file
3. Store the key in a Kubernetes Secret
4. Mount the Secret in your pod
5. Set `GOOGLE_APPLICATION_CREDENTIALS` env var

This is insecure (key files can leak, no rotation, hard to audit).

**With Workload Identity:**
1. Create a GCP service account: `backend-sa@PROJECT.iam.gserviceaccount.com`
2. Create a Kubernetes service account: `backend-sa` in `default` namespace
3. Bind them: `gcloud iam service-accounts add-iam-policy-binding backend-sa@PROJECT.iam.gserviceaccount.com --role=roles/iam.workloadIdentityUser --member="serviceAccount:PROJECT.svc.id.goog[default/backend-sa]"`
4. Annotate K8s service account: `kubectl annotate serviceaccount backend-sa iam.gke.io/gcp-service-account=backend-sa@PROJECT.iam.gserviceaccount.com`
5. Run pod with `serviceAccountName: backend-sa`

Now the pod can authenticate to GCP services using Application Default Credentials (no key file).

**IAM Roles for AI Doctor:**
- Backend: `roles/secretmanager.secretAccessor` (read secrets)
- Backend: `roles/logging.logWriter` (write logs, though GKE does this by default)

### Cloud Logging & Monitoring

**Cloud Logging (formerly Stackdriver Logging):**
Centralized log aggregation. All pod stdout/stderr is automatically sent to Cloud Logging.

**Query logs:**
```bash
gcloud logging read "resource.type=k8s_container AND resource.labels.namespace_name=default" --limit 50
```

Or use the web console: Logging > Logs Explorer, filter by `resource.type="k8s_container"`, add filters for namespace, pod name, container name.

**Cloud Monitoring (formerly Stackdriver Monitoring):**
Metrics collection and dashboards. GKE sends these metrics automatically:
- CPU/memory usage per pod
- Network traffic per pod
- Disk I/O per node
- Cluster-level metrics (total pods, pending pods)

**Pricing:**
- First 50GB/month of logs: free
- First 1GB/month of monitoring data: free
- AI Doctor uses <1GB/mo of logs in dev, so effectively free

**Alerts:**
Set up alerts in Cloud Monitoring:
- Alert if pod CPU > 80% for 5 minutes
- Alert if pod restarts > 3 times in 10 minutes

### VPC (Virtual Private Cloud) / Networking

**VPC:**
GCP's software-defined network. When you create a GKE cluster, you choose a VPC and subnets.

**VPC-native GKE:**
Pods get IP addresses from a secondary IP range on the subnet (called "alias IPs"). Benefits:
- Pods are directly routable within the VPC (no NAT)
- VPC firewall rules apply to pod IPs
- Private Google Access: pods can reach GCP APIs (storage.googleapis.com) without going through public internet

**IP ranges in VPC-native cluster:**
- Node subnet: e.g., `10.0.0.0/24` (256 IPs for nodes)
- Pod IP range: e.g., `10.4.0.0/14` (262k IPs for pods)
- Service IP range: e.g., `10.8.0.0/20` (4096 IPs for Services)

**Ingress and Load Balancers:**
When you create an Ingress in GKE, Google provisions a global HTTP(S) Load Balancer:
- Anycast IP (low latency from anywhere in the world)
- SSL termination (upload your cert or use Google-managed certs)
- URL-based routing (route `/api/*` to backend Service, `/*` to frontend Service)

**Pricing:**
- Global HTTP(S) LB: $18/mo base + $0.008/GB processed
- Network egress: $0.12/GB (within GCP, same region), $0.19-0.23/GB (internet)

---

## 5. GKE Setup Commands (gcloud CLI Walkthrough)

This section walks through creating a GKE Autopilot cluster, setting up Artifact Registry, and connecting kubectl.

### Prerequisites

**Install gcloud CLI:**
- macOS: `brew install google-cloud-sdk`
- Linux: `curl https://sdk.cloud.google.com | bash`
- Windows: Download installer from https://cloud.google.com/sdk/docs/install

**Install kubectl:**
gcloud includes kubectl, but you can also install via:
```bash
gcloud components install kubectl
```

**Authenticate:**
```bash
gcloud auth login
```

This opens a browser for OAuth login. After authenticating, set your project:
```bash
gcloud config set project PROJECT_ID
```

Replace `PROJECT_ID` with your GCP project ID (visible in the GCP console header).

**Verify:**
```bash
gcloud config list
```

Should show your account and project.

### Step 1: Enable Required APIs

GCP disables most APIs by default. Enable the ones we need:

```bash
# Kubernetes Engine API (for GKE)
gcloud services enable container.googleapis.com

# Artifact Registry API (for container images)
gcloud services enable artifactregistry.googleapis.com

# Compute Engine API (for VMs, load balancers)
gcloud services enable compute.googleapis.com

# Cloud Logging and Monitoring (usually enabled by default)
gcloud services enable logging.googleapis.com
gcloud services enable monitoring.googleapis.com
```

Each command takes ~30 seconds. Verify:
```bash
gcloud services list --enabled | grep -E 'container|artifact|compute'
```

### Step 2: Create Artifact Registry Repository

Create a Docker repository to store backend and frontend images:

```bash
gcloud artifacts repositories create doctor-app \
  --repository-format=docker \
  --location=us-central1 \
  --description="AI Doctor Assistant container images"
```

**Parameters:**
- `--repository-format=docker`: Store Docker images (other options: `maven`, `npm`, `python`)
- `--location=us-central1`: Same region as our GKE cluster (minimizes latency and egress cost)

**Verify:**
```bash
gcloud artifacts repositories list --location=us-central1
```

**Configure Docker to authenticate:**
```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
```

This adds credentials to `~/.docker/config.json` so `docker push` works without manual login.

### Step 3: Create GKE Autopilot Cluster

Create a zonal Autopilot cluster in us-central1-a:

```bash
gcloud container clusters create-auto doctor-cluster \
  --region=us-central1 \
  --project=PROJECT_ID \
  --release-channel=regular \
  --enable-stackdriver-kubernetes \
  --enable-ip-alias \
  --network=default \
  --subnetwork=default \
  --cluster-version=latest
```

**Parameters explained:**
- `create-auto`: Create Autopilot cluster (use `create` for Standard cluster)
- `--region=us-central1`: Regional cluster (control plane in 3 zones, nodes in 3 zones). Use `--zone=us-central1-a` for zonal cluster (cheaper but no HA).
- `--release-channel=regular`: Auto-upgrade to stable Kubernetes versions. Options: `rapid`, `regular`, `stable`.
- `--enable-stackdriver-kubernetes`: Send logs and metrics to Cloud Logging/Monitoring (default for GKE).
- `--enable-ip-alias`: VPC-native cluster (default for Autopilot).
- `--network=default` / `--subnetwork=default`: Use default VPC. Replace with custom VPC if you created one.
- `--cluster-version=latest`: Use latest available Kubernetes version in the release channel.

**This command takes 5-10 minutes.** Progress is shown in terminal. When done, you'll see:
```
Created [https://container.googleapis.com/v1/projects/PROJECT/zones/us-central1/clusters/doctor-cluster].
```

**For a cheaper zonal cluster:**
```bash
gcloud container clusters create-auto doctor-cluster \
  --zone=us-central1-a \
  --project=PROJECT_ID
```

Zonal cluster has no management fee, but control plane and nodes are in a single zone (no HA).

### Step 4: Get Cluster Credentials

Connect kubectl to the new cluster:

```bash
gcloud container clusters get-credentials doctor-cluster \
  --region=us-central1 \
  --project=PROJECT_ID
```

This updates `~/.kube/config` with cluster endpoint and authentication token.

**Verify:**
```bash
kubectl config current-context
```

Should show:
```
gke_PROJECT_ID_us-central1_doctor-cluster
```

**Check nodes:**
```bash
kubectl get nodes
```

In Autopilot, you'll see 0-2 nodes initially (Google provisions nodes as you create pods). In Standard, you'll see nodes in your node pool.

**Check cluster info:**
```bash
kubectl cluster-info
```

Should show:
```
Kubernetes control plane is running at https://X.X.X.X
GLBCDefaultBackend is running at https://X.X.X.X/api/v1/namespaces/kube-system/services/default-http-backend:http/proxy
...
```

### Step 5: Verify Cluster and Deploy Test Pod

Create a test pod to verify the cluster works:

```bash
kubectl run nginx-test --image=nginx:latest --port=80
```

Wait for it to be ready:
```bash
kubectl get pod nginx-test
```

Should show `STATUS: Running` after ~30 seconds (Autopilot provisions a node on-demand).

**Check logs:**
```bash
kubectl logs nginx-test
```

**Expose it as a LoadBalancer Service (for testing):**
```bash
kubectl expose pod nginx-test --type=LoadBalancer --name=nginx-lb
```

Wait for external IP:
```bash
kubectl get service nginx-lb --watch
```

After 2-3 minutes, `EXTERNAL-IP` changes from `<pending>` to a public IP. Open it in a browser to see the Nginx welcome page.

**Clean up:**
```bash
kubectl delete pod nginx-test
kubectl delete service nginx-lb
```

### Step 6: Build and Push Images to Artifact Registry

From the AI Doctor Assistant repo root:

```bash
# Build backend image
cd backend
docker build -t us-central1-docker.pkg.dev/PROJECT_ID/doctor-app/backend:v1.0.0 .

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/PROJECT_ID/doctor-app/backend:v1.0.0

# Build frontend image
cd ../frontend
docker build -t us-central1-docker.pkg.dev/PROJECT_ID/doctor-app/frontend:v1.0.0 .

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/PROJECT_ID/doctor-app/frontend:v1.0.0
```

**Verify:**
```bash
gcloud artifacts docker images list us-central1-docker.pkg.dev/PROJECT_ID/doctor-app
```

Should show `backend:v1.0.0` and `frontend:v1.0.0`.

### Step 7: Deploy AI Doctor Assistant to GKE

Create Kubernetes manifests (covered in document 04), then:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/frontend.yaml
kubectl apply -f k8s/ingress.yaml
```

Wait for pods to be ready:
```bash
kubectl get pods -n default --watch
```

Get the Ingress external IP:
```bash
kubectl get ingress -n default
```

Access the app at the Ingress IP.

---

## 6. Why Kubernetes Over Cloud Run / Cloud Functions

GCP offers simpler serverless options for deploying containers and code. Why use Kubernetes?

### Comparison Table

| Aspect | Cloud Run | Cloud Functions | GKE (Kubernetes) |
|--------|-----------|-----------------|-------------------|
| **Pricing model** | Pay per request + CPU/memory during request | Pay per invocation + GB-seconds | Pay per pod resource (Autopilot) or node VM (Standard) |
| **Cold starts** | Yes (~1-3 seconds for containers) | Yes (~1-5 seconds for Python) | No (pods stay warm) |
| **Persistent storage** | No (ephemeral filesystem) | No (ephemeral) | Yes (Persistent Volumes) |
| **Multi-container pods** | No (single container per service) | No (single function) | Yes (sidecars, init containers) |
| **Stateful workloads** | Not ideal | Not supported | Supported (StatefulSets) |
| **GPU support** | No | No | Yes (Autopilot and Standard) |
| **Networking** | HTTP(S) ingress only | HTTP(S) ingress only | Full control (TCP, UDP, gRPC) |
| **Agent isolation** | Hard (would need separate Cloud Run services) | Hard (separate functions) | Easy (separate Deployments) |
| **Portability** | GCP-specific | GCP-specific | Standard Kubernetes (runs anywhere) |
| **Complexity** | Low (deploy container, done) | Low (deploy code, done) | High (learn Pods, Services, Ingress, PVCs) |
| **Scaling** | Automatic (0-1000+ instances) | Automatic | Configure HPA or use Autopilot auto-scaling |
| **Best for** | Stateless web apps, APIs | Event-driven functions (Pub/Sub, Cloud Storage triggers) | Complex multi-service apps, stateful workloads, learning K8s |

### Why GKE for AI Doctor Assistant

**1. Persistent PostgreSQL**

Cloud Run and Cloud Functions have ephemeral filesystems. Every container restart loses data. While you could use Cloud SQL with these services, we're avoiding Cloud SQL initially to save cost. Running PostgreSQL in Kubernetes with a Persistent Volume is the most cost-effective solution.

**2. Future GPU Support**

AI Doctor may eventually use local models (e.g., LLaMA for triage before calling Claude). GKE supports GPU node pools and GPU-attached pods. Cloud Run and Cloud Functions don't support GPUs.

**3. Agent Isolation**

Future versions will have multiple AI agents (diagnostic agent, prescription agent, triage agent). In Kubernetes, each agent runs as a separate Deployment, making it easy to scale, update, and isolate them. In Cloud Run, you'd need separate Cloud Run services, each with its own endpoint and IAM configuration.

**4. Learning Goal**

The goal of this project includes learning Kubernetes. Using Cloud Run would skip the orchestration, networking, and storage concepts that K8s teaches.

**5. Portability**

If you want to move off GCP (to AWS EKS, Azure AKS, or on-prem), Kubernetes manifests are portable. Cloud Run is GCP-specific.

**6. Full Control**

Kubernetes gives you control over networking (Services, NetworkPolicies), storage (StorageClasses, PVCs), and scheduling (node affinity, taints/tolerations). Cloud Run abstracts this away, which is convenient until you need fine-grained control.

### When Cloud Run or Cloud Functions Make Sense

**Use Cloud Run if:**
- Your app is stateless (no database, or using Cloud SQL)
- You want zero-ops (no cluster management)
- Traffic is spiky (long idle periods)
- You're okay with cold starts

**Use Cloud Functions if:**
- You're building event-driven workflows (e.g., "when a file is uploaded to Cloud Storage, process it")
- Code is simple (single function, <10 minutes execution time)
- You don't want to manage Docker images

**Use GKE if:**
- You need stateful workloads (databases, caches)
- You want multi-container orchestration
- You need GPUs
- You're building microservices
- Learning Kubernetes is a goal

For AI Doctor, GKE is the right choice despite the added complexity.

---

## Summary

**GKE provides:**
- Managed Kubernetes control plane (no etcd management)
- Auto-upgrades, auto-repair, integrated logging/monitoring
- VPC-native networking (pods as first-class VPC citizens)
- Workload Identity (secure GCP service authentication)
- Two modes: Autopilot (pay per pod resource) vs Standard (pay per node VM)

**Autopilot is ideal for:**
- Variable or unpredictable load
- Dev/test environments
- Workloads that don't need privileged containers

**Standard is ideal for:**
- Predictable baseline load
- Need for privileged containers or specific node types
- Full control over node configuration

**AI Doctor Assistant costs:**
- Autopilot: ~$102/mo (pay per pod resource)
- Standard zonal: ~$44/mo (1 e2-medium node + overhead)
- Standard regional: ~$165/mo (HA across 3 zones)

**GCP services used:**
- Artifact Registry: store Docker images (~$0.50/mo)
- Secret Manager: store API keys (optional, <$1/mo)
- Cloud SQL: managed PostgreSQL (future migration, $25-50/mo for decent perf)
- Workload Identity: secure pod-to-GCP authentication
- Cloud Logging/Monitoring: centralized logs and metrics (first 50GB free)

**Why GKE over Cloud Run:**
- Need persistent PostgreSQL (PVC)
- Future GPU support
- Agent isolation (separate Deployments)
- Learning Kubernetes is a goal
- Portability (K8s is standard)

**Next document:** 04 — Writing Kubernetes Manifests (Deployments, Services, Ingress, PVCs)

---

**Further Reading:**
- GKE Autopilot overview: https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview
- GKE pricing: https://cloud.google.com/kubernetes-engine/pricing
- Workload Identity setup: https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity
- VPC-native clusters: https://cloud.google.com/kubernetes-engine/docs/concepts/alias-ips
