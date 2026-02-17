# The Kubernetes Tool Ecosystem

This document maps the complete toolchain for developing, deploying, and operating the AI Doctor Assistant on Kubernetes. Understanding when and why to use each tool prevents confusion and builds a mental model of the deployment pipeline.

---

## Tool Lifecycle: Development to Production

The journey from code to running container follows this flow:

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
│   IDE    │ -> │  Docker  │ -> │   Registry   │ -> │  Kubernetes  │ -> │ Monitor  │
│          │    │  Build   │    │ (Artifact    │    │   Deploy     │    │          │
│ VS Code  │    │          │    │  Registry)   │    │              │    │  Logs    │
│          │    │ buildx   │    │              │    │ kubectl      │    │  k9s     │
│ Write    │    │ docker   │    │ gcloud push  │    │ kustomize    │    │  GCP     │
│ Code     │    │ build    │    │              │    │ ArgoCD       │    │  Console │
└──────────┘    └──────────┘    └──────────────┘    └──────────────┘    └──────────┘
     |               |                 |                    |                  |
     v               v                 v                    v                  v
  Iterate      Create Image      Store Image         Run Containers      Observe
  Locally      Tag & Build       Push to Cloud       Apply Manifests     Debug
```

Each tool has a specific role. Mixing them up (e.g., trying to manage GCP IAM with kubectl) leads to confusion.

---

## gcloud CLI: The GCP Control Plane

**Purpose:** Manage Google Cloud Platform resources (projects, clusters, registries, IAM). Think of gcloud as the infrastructure layer — it provisions the playground where Kubernetes runs.

**Relationship to kubectl:**
- **gcloud**: creates and manages the cluster itself (nodes, networking, IAM, registries)
- **kubectl**: manages what runs INSIDE the cluster (pods, deployments, services)

Analogy: gcloud builds the stadium, kubectl coaches the team playing in it.

### Authentication

Two modes of authentication:

```bash
# User authentication (for interactive CLI use)
gcloud auth login

# Application default credentials (for applications/scripts)
gcloud auth application-default login
```

**When to use which:**
- `gcloud auth login`: for your daily CLI work
- `application-default`: for local dev when apps need GCP API access (e.g., pushing images, accessing Cloud Storage)

### Essential gcloud Commands

#### Project and Configuration

```bash
# Set active project (all subsequent commands use this project)
gcloud config set project doctor-assistant-prod

# View current configuration
gcloud config list

# List all projects
gcloud projects list
```

#### Cluster Management

```bash
# Create GKE Autopilot cluster (managed nodes, auto-scaling)
gcloud container clusters create-auto doctor-cluster \
  --region=us-central1 \
  --project=doctor-assistant-prod

# Get credentials (populates ~/.kube/config with cluster connection info)
gcloud container clusters get-credentials doctor-cluster \
  --region=us-central1 \
  --project=doctor-assistant-prod

# List clusters
gcloud container clusters list

# Delete cluster (careful — destroys everything)
gcloud container clusters delete doctor-cluster --region=us-central1
```

**What "get-credentials" does:**
- Adds a new context to your `~/.kube/config` file
- Context = cluster endpoint + CA certificate + auth method
- After running, `kubectl` commands target this cluster

#### Artifact Registry (Container Images)

```bash
# Create a Docker repository in Artifact Registry
gcloud artifacts repositories create docker-repo \
  --repository-format=docker \
  --location=us-central1 \
  --description="AI Doctor Assistant images"

# List repositories
gcloud artifacts repositories list --location=us-central1

# List images in a repository
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/doctor-assistant-prod/docker-repo

# Configure Docker to authenticate with Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev
```

#### IAM and Service Accounts

```bash
# Create service account for application
gcloud iam service-accounts create doctor-backend-sa \
  --display-name="Doctor Backend Service Account"

# Grant roles to service account
gcloud projects add-iam-policy-binding doctor-assistant-prod \
  --member="serviceAccount:doctor-backend-sa@doctor-assistant-prod.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

# List service accounts
gcloud iam service-accounts list
```

### When to Use gcloud

- Creating/deleting GKE clusters
- Managing Artifact Registry (image storage)
- Configuring IAM roles and service accounts
- Setting up Cloud SQL, Secret Manager, Cloud Storage
- Viewing billing, quotas, project settings

**Never use gcloud for:** deploying application code, managing pods/deployments, viewing logs from running containers (that's kubectl's job).

---

## kubectl: The Kubernetes Client

**Purpose:** The primary CLI for interacting with any Kubernetes cluster (GKE, EKS, local Minikube, etc.). Every kubectl command is an HTTP request to the Kubernetes API server.

### kubeconfig and Contexts

kubectl reads `~/.kube/config` to know which cluster to talk to. This file contains:

```yaml
clusters:               # cluster endpoints and CA certificates
- name: gke_doctor-assistant-prod_us-central1_doctor-cluster
  cluster:
    server: https://34.123.45.67
    certificate-authority-data: LS0tLS1...

users:                  # authentication methods (tokens, certs, gcloud)
- name: gke_user
  user:
    exec:               # uses gcloud to get fresh auth token
      command: gcloud
      args: [config, config-helper, --format=json]

contexts:               # cluster + user + default namespace
- name: gke-prod
  context:
    cluster: gke_doctor-assistant-prod_us-central1_doctor-cluster
    user: gke_user
    namespace: doctor-app
```

**Context = cluster + user + namespace.** It's a saved configuration so you don't have to type cluster/user/namespace every time.

#### Managing Contexts

```bash
# List all contexts
kubectl config get-contexts

# Switch to a different context
kubectl config use-context gke-prod

# View current context
kubectl config current-context

# Set default namespace for current context
kubectl config set-context --current --namespace=doctor-app
```

**Best practice:** create separate contexts for dev/staging/prod to avoid accidental deploys to the wrong environment.

### Essential kubectl Commands

#### Viewing Resources

```bash
# List pods in a namespace
kubectl get pods -n doctor-app

# Wide output (shows node, IP, status details)
kubectl get pods -n doctor-app -o wide

# All resources in namespace
kubectl get all -n doctor-app

# Deployments
kubectl get deployments -n doctor-app

# Services (networking)
kubectl get services -n doctor-app

# ConfigMaps and Secrets
kubectl get configmaps -n doctor-app
kubectl get secrets -n doctor-app

# Describe (detailed info, events, status)
kubectl describe pod doctor-backend-7d8f5c9-xkzqp -n doctor-app
kubectl describe deployment doctor-backend -n doctor-app
```

**Output formats:**
- `-o wide`: extra columns (node, IP, etc.)
- `-o yaml`: full resource definition
- `-o json`: JSON format (for scripting/jq)
- `-o jsonpath='{.status.phase}'`: extract specific fields

#### Creating and Updating Resources

```bash
# Apply a manifest file
kubectl apply -f backend-deployment.yaml

# Apply all manifests in a directory
kubectl apply -f infra/k8s/base/

# Apply Kustomize overlay
kubectl apply -k infra/k8s/overlays/dev/

# Update deployment image (quick rollout)
kubectl set image deployment/doctor-backend \
  backend=us-central1-docker.pkg.dev/doctor-assistant-prod/docker-repo/backend:v1.2.0 \
  -n doctor-app

# Scale replicas
kubectl scale deployment doctor-backend --replicas=3 -n doctor-app
```

**apply vs create:**
- `kubectl apply`: idempotent, can be run multiple times (updates existing resources)
- `kubectl create`: fails if resource exists (rarely used, apply is preferred)

#### Debugging Commands

```bash
# View logs (most recent)
kubectl logs doctor-backend-7d8f5c9-xkzqp -n doctor-app

# Follow logs (live tail)
kubectl logs -f doctor-backend-7d8f5c9-xkzqp -n doctor-app

# Previous container logs (if pod crashed and restarted)
kubectl logs doctor-backend-7d8f5c9-xkzqp -n doctor-app --previous

# All containers in pod (if multiple containers)
kubectl logs doctor-backend-7d8f5c9-xkzqp -n doctor-app --all-containers

# Shell into running container
kubectl exec -it doctor-backend-7d8f5c9-xkzqp -n doctor-app -- /bin/sh

# Run a command in container
kubectl exec doctor-backend-7d8f5c9-xkzqp -n doctor-app -- env

# Port-forward to access service locally
kubectl port-forward svc/doctor-backend 8000:8000 -n doctor-app
# Now: http://localhost:8000 → backend service in cluster

# Resource usage (requires metrics-server)
kubectl top pods -n doctor-app
kubectl top nodes
```

#### Rollouts and History

```bash
# View rollout status
kubectl rollout status deployment/doctor-backend -n doctor-app

# Rollout history (past revisions)
kubectl rollout history deployment/doctor-backend -n doctor-app

# Rollback to previous version
kubectl rollout undo deployment/doctor-backend -n doctor-app

# Rollback to specific revision
kubectl rollout undo deployment/doctor-backend --to-revision=3 -n doctor-app

# Pause rollout (for testing)
kubectl rollout pause deployment/doctor-backend -n doctor-app

# Resume rollout
kubectl rollout resume deployment/doctor-backend -n doctor-app
```

#### Dangerous Commands (Use with Caution)

```bash
# Delete a pod (will be recreated by deployment controller)
kubectl delete pod doctor-backend-7d8f5c9-xkzqp -n doctor-app

# Delete a deployment (destroys all pods)
kubectl delete deployment doctor-backend -n doctor-app

# Delete entire namespace (DESTROYS EVERYTHING INSIDE)
kubectl delete namespace doctor-app

# Force delete stuck pod
kubectl delete pod doctor-backend-7d8f5c9-xkzqp -n doctor-app --grace-period=0 --force
```

**Safety tip:** Always specify `-n <namespace>` explicitly. Default namespace is `default`, which can lead to confusion.

---

## k9s: Terminal UI for Kubernetes

**Purpose:** An interactive terminal dashboard for exploring and managing Kubernetes clusters. Think of it as "htop for Kubernetes" — faster than typing kubectl commands repeatedly.

### Installation

```bash
# macOS
brew install k9s

# Linux
curl -sS https://webi.sh/k9s | sh
```

### Why k9s?

kubectl is great for scripting and one-off commands, but exploring a cluster interactively is tedious:

```bash
# kubectl approach (many commands)
kubectl get pods -n doctor-app
kubectl describe pod doctor-backend-7d8f5c9-xkzqp -n doctor-app
kubectl logs doctor-backend-7d8f5c9-xkzqp -n doctor-app
kubectl get deployments -n doctor-app
kubectl describe deployment doctor-backend -n doctor-app
```

**k9s approach:** open k9s, type `:pods`, press Enter, arrow-key to pod, press `l` for logs, `d` for describe, `s` for shell. One tool, keyboard-driven, instant feedback.

### Key Navigation

Launch k9s: `k9s -n doctor-app` (starts in doctor-app namespace)

**Resource views (type colon + resource name):**
- `:pods` or `:po` → list pods
- `:deployments` or `:deploy` → list deployments
- `:services` or `:svc` → list services
- `:configmaps` or `:cm` → list configmaps
- `:secrets` or `:sec` → list secrets
- `:namespaces` or `:ns` → list namespaces
- `:nodes` → list cluster nodes

**Actions (press key while resource is highlighted):**
- `l` → view logs
- `d` → describe resource
- `e` → edit resource (opens YAML in $EDITOR)
- `s` → shell into pod
- `ctrl-d` → delete resource (confirms first)
- `y` → view YAML
- `Enter` → drill down (e.g., deployment → replicaset → pods)

**Navigation:**
- `/` → filter resources (regex)
- `Esc` → clear filter or go back
- `?` → help screen
- `:xray <resource> <name>` → visualize hierarchy (deployment → replicaset → pod)
- `:q` or `:quit` → exit

**Namespace switching:**
- `:ns` → list namespaces, press Enter on one to switch
- Or launch with `-n <namespace>` flag

### Example Workflow

**Scenario:** backend pod is crashing, need to debug.

1. `k9s -n doctor-app`
2. `:pods` → see list of pods
3. Arrow-key to `doctor-backend-7d8f5c9-xkzqp` (status: CrashLoopBackOff)
4. Press `l` → view logs (see error: "Database connection refused")
5. Press `Esc` → back to pod list
6. `:svc` → list services
7. Arrow-key to `postgres` service, press `d` → describe (confirm endpoints exist)
8. `:pods` → back to pods
9. Press `s` on backend pod → shell into container
10. Run `ping postgres.doctor-app.svc.cluster.local` (test DNS resolution)

All of this without typing `kubectl` once. Faster for interactive debugging.

### When to Use k9s vs kubectl

| Task | Use k9s | Use kubectl | Reason |
|------|---------|-------------|--------|
| Exploring cluster state | ✓ | | Visual, fast navigation |
| Watching logs live | ✓ | | Split-screen, easy switching |
| Port-forwarding | ✓ | | Interactive selection |
| Scripting/automation | | ✓ | kubectl output is parseable |
| CI/CD pipelines | | ✓ | k9s is interactive, not scriptable |
| Quick one-off commands | | ✓ | kubectl is faster for single commands |

**Best practice:** use k9s for debugging and exploration, kubectl for automation and scripting.

---

## Helm: Package Manager for Kubernetes

**Purpose:** Bundle Kubernetes manifests into reusable "charts" (like npm packages or apt packages, but for K8s applications).

### What is a Helm Chart?

A chart is a directory structure containing:

```
my-chart/
├── Chart.yaml              # metadata (name, version, description)
├── values.yaml             # default configuration values
├── templates/              # templated K8s manifests
│   ├── deployment.yaml     # uses {{ .Values.replicaCount }}
│   ├── service.yaml        # uses {{ .Values.service.port }}
│   ├── ingress.yaml
│   └── _helpers.tpl        # template functions
└── charts/                 # sub-charts (dependencies)
```

**values.yaml:**
```yaml
replicaCount: 2

image:
  repository: my-app
  tag: "1.0.0"

service:
  type: ClusterIP
  port: 80
```

**templates/deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}
spec:
  replicas: {{ .Values.replicaCount }}
  template:
    spec:
      containers:
      - name: app
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
```

Helm renders the templates by substituting `{{ .Values.* }}` with actual values, then applies the resulting manifests to the cluster.

### When to Use Helm

**✓ Installing third-party software:**
- PostgreSQL, Redis, RabbitMQ
- Ingress controllers (nginx, Traefik)
- Monitoring (Prometheus, Grafana)
- CI/CD tools (ArgoCD, Jenkins)
- Cert-manager (automatic TLS certificates)

**Example:** Install PostgreSQL in AI Doctor Assistant:

```bash
# Add Bitnami chart repository
helm repo add bitnami https://charts.bitnami.com/bitnami

# Search for postgres charts
helm search repo postgresql

# Install postgres with custom values
helm install postgres bitnami/postgresql \
  --namespace doctor-app \
  --create-namespace \
  --values postgres-values.yaml
```

**postgres-values.yaml:**
```yaml
auth:
  postgresPassword: "doctor-secret-123"
  database: "doctor_db"

primary:
  persistence:
    size: 10Gi

metrics:
  enabled: true
```

One command installs: StatefulSet, Service, PersistentVolumeClaim, ConfigMap, Secrets.

### When NOT to Use Helm

**✗ For your own application manifests:**
- Helm templates use Go templating syntax (`{{ if .Values.feature.enabled }}`)
- Templates are ugly, error-prone, hard to validate
- You don't need reusability across 100 projects (you have 1 app)
- Plain YAML + Kustomize is simpler, more maintainable

**AI Doctor Assistant approach:**
- **Helm:** PostgreSQL, ArgoCD, nginx-ingress (third-party, complex, need configurability)
- **Kustomize:** backend, frontend (our code, base + overlays, no templating)

### Essential Helm Commands

```bash
# Add chart repository
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add argo https://argoproj.github.io/argo-helm

# Update repositories (fetch latest chart versions)
helm repo update

# Search for charts
helm search repo postgres
helm search hub nginx  # search Artifact Hub (public charts)

# Install a chart
helm install <release-name> <chart> [flags]
helm install postgres bitnami/postgresql \
  -n doctor-app \
  --values postgres-values.yaml

# List installed releases
helm list -n doctor-app
helm list --all-namespaces

# Upgrade a release (change configuration or chart version)
helm upgrade postgres bitnami/postgresql \
  -n doctor-app \
  --values postgres-values.yaml

# Rollback to previous version
helm rollback postgres 1 -n doctor-app

# Uninstall (deletes all resources)
helm uninstall postgres -n doctor-app

# Preview rendered templates (dry-run)
helm template postgres bitnami/postgresql --values postgres-values.yaml

# Show chart information
helm show chart bitnami/postgresql
helm show values bitnami/postgresql  # see all configurable values
```

### Helm Release Lifecycle

```
helm install    → release created (revision 1)
helm upgrade    → new revision (revision 2, 3, ...)
helm rollback   → revert to previous revision
helm uninstall  → release deleted, resources removed
```

Each upgrade creates a new revision. Rollback reverts to a previous revision's configuration.

---

## Kustomize: Overlay-Based YAML Customization

**Purpose:** Customize Kubernetes YAML manifests without templating. Compose base configurations and apply environment-specific overlays (patches).

### Why Kustomize over Helm for Own Apps?

| Feature | Helm | Kustomize |
|---------|------|-----------|
| Templating language | Go templates (`{{ .Values.x }}`) | None (plain YAML) |
| Reusability | Across many projects | Within one project (base + overlays) |
| Complexity | High (templates, functions, conditionals) | Low (merge patches) |
| Validation | Hard (templates aren't valid YAML) | Easy (plain YAML, validate with kubectl) |
| Built into kubectl | No | Yes (`kubectl apply -k`) |

**Kustomize philosophy:** Start with plain, valid K8s YAML. Apply patches to customize per environment. No magic, no templating.

### Base + Overlays Pattern

```
infra/k8s/
├── base/                           # shared resources (dev + staging + prod)
│   ├── kustomization.yaml          # lists resources in base
│   ├── namespace.yaml              # doctor-app namespace
│   ├── backend-deployment.yaml     # 2 replicas, image: backend:latest
│   ├── backend-service.yaml        # ClusterIP service
│   ├── frontend-deployment.yaml    # 2 replicas, image: frontend:latest
│   ├── frontend-service.yaml       # ClusterIP service
│   └── postgres-statefulset.yaml   # PostgreSQL StatefulSet
│
└── overlays/
    ├── dev/                        # dev-specific patches
    │   ├── kustomization.yaml      # references base + patches
    │   ├── replica-patch.yaml      # 1 replica for dev
    │   └── configmap-patch.yaml    # DEBUG=true for dev
    │
    ├── staging/                    # staging-specific patches
    │   ├── kustomization.yaml
    │   ├── replica-patch.yaml      # 2 replicas
    │   └── configmap-patch.yaml    # DEBUG=false, RATE_LIMIT=100
    │
    └── prod/                       # production patches
        ├── kustomization.yaml
        ├── replica-patch.yaml      # 5 replicas
        ├── configmap-patch.yaml    # DEBUG=false, RATE_LIMIT=1000
        └── hpa.yaml                # HorizontalPodAutoscaler (prod only)
```

### Example: base/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: doctor-app

resources:
  - namespace.yaml
  - backend-deployment.yaml
  - backend-service.yaml
  - frontend-deployment.yaml
  - frontend-service.yaml
  - postgres-statefulset.yaml

commonLabels:
  app: doctor-assistant
  version: v1
```

### Example: overlays/dev/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

bases:
  - ../../base

patchesStrategicMerge:
  - replica-patch.yaml
  - configmap-patch.yaml

images:
  - name: backend
    newName: us-central1-docker.pkg.dev/doctor-assistant-dev/docker-repo/backend
    newTag: dev-abc123f
```

### Example: overlays/dev/replica-patch.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: doctor-backend
spec:
  replicas: 1  # override base (base has 2)
```

**Strategic merge:** Kustomize intelligently merges this patch with the base deployment. Only `replicas` changes; everything else stays the same.

### Example: overlays/staging/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

bases:
  - ../../base

patchesStrategicMerge:
  - replica-patch.yaml
  - configmap-patch.yaml

images:
  - name: backend
    newName: us-central1-docker.pkg.dev/doctor-assistant-staging/docker-repo/backend
    newTag: v1.2.3

commonAnnotations:
  environment: staging
```

### Essential Kustomize Commands

```bash
# Preview rendered manifests (without applying)
kubectl kustomize infra/k8s/overlays/dev/

# Apply overlay to cluster
kubectl apply -k infra/k8s/overlays/dev/

# View diff before applying
kubectl kustomize infra/k8s/overlays/staging/ | kubectl diff -f -

# Delete resources managed by kustomize
kubectl delete -k infra/k8s/overlays/dev/
```

### Kustomize Features

**1. Strategic merge patches** (shown above): partial resource definitions, merged intelligently.

**2. JSON patches** (for precise edits):
```yaml
patchesJson6902:
  - target:
      group: apps
      version: v1
      kind: Deployment
      name: doctor-backend
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 3
```

**3. Image tag updates** (common in CI/CD):
```yaml
images:
  - name: backend
    newTag: v1.3.0  # change tag without editing deployment YAML
```

**4. ConfigMap/Secret generators** (from files):
```yaml
configMapGenerator:
  - name: app-config
    files:
      - application.properties
```

**5. Name prefixes/suffixes** (for unique resource names):
```yaml
namePrefix: dev-
nameSuffix: -v2
```

**6. Common labels/annotations** (applied to all resources):
```yaml
commonLabels:
  team: backend
  project: doctor-assistant
```

### AI Doctor Assistant Kustomize Workflow

1. **Base:** Define core manifests (deployments, services, statefulsets)
2. **Dev overlay:** 1 replica, debug mode, local image tags
3. **Staging overlay:** 2 replicas, staging image tags, closer to prod config
4. **Prod overlay:** 5+ replicas, autoscaling, prod image tags, tight resource limits

**Deployment command:**
```bash
# Dev
kubectl apply -k infra/k8s/overlays/dev/

# Staging
kubectl apply -k infra/k8s/overlays/staging/

# Prod
kubectl apply -k infra/k8s/overlays/prod/
```

---

## ArgoCD: GitOps Continuous Delivery

**Purpose:** Continuously synchronize Kubernetes cluster state with a Git repository. Git is the source of truth; ArgoCD ensures the cluster matches.

### GitOps Philosophy

**Traditional CI/CD (push-based):**
```
GitHub Actions → docker build → docker push → kubectl apply
```
Problem: GitHub Actions needs cluster credentials (security risk), pipeline failures leave cluster in unknown state.

**GitOps with ArgoCD (pull-based):**
```
GitHub Actions → docker build → docker push → update manifest in Git
ArgoCD (in cluster) → detects Git change → kubectl apply
```
Benefits:
- Cluster credentials stay in cluster (never leak to CI/CD)
- Git history = deployment history (audit trail)
- Rollback = revert Git commit
- Declarative: "cluster should match this Git commit" (not imperative: "run these kubectl commands")

### How ArgoCD Works

1. **Define an Application** (ArgoCD resource):
   ```yaml
   apiVersion: argoproj.io/v1alpha1
   kind: Application
   metadata:
     name: doctor-backend-staging
     namespace: argocd
   spec:
     project: default
     source:
       repoURL: https://github.com/your-org/ai-doctor-assistant.git
       targetRevision: main
       path: infra/k8s/overlays/staging
     destination:
       server: https://kubernetes.default.svc
       namespace: doctor-app
     syncPolicy:
       automated:
         prune: true      # delete resources removed from Git
         selfHeal: true   # revert manual kubectl changes
   ```

2. **ArgoCD watches Git repo:**
   - Polls every 3 minutes (configurable)
   - Webhook support for instant sync on push

3. **Detects drift:**
   - Compares desired state (Git) vs actual state (cluster)
   - Shows diff in web UI

4. **Syncs automatically** (if `automated` enabled):
   - Applies changes to cluster
   - Reports status (healthy, degraded, syncing)

### Installation

```bash
# Install ArgoCD via Helm
helm repo add argo https://argoproj.github.io/argo-helm
helm install argocd argo/argo-cd \
  --namespace argocd \
  --create-namespace

# Get admin password
kubectl get secret argocd-initial-admin-secret \
  -n argocd \
  -o jsonpath="{.data.password}" | base64 --decode

# Port-forward to access UI
kubectl port-forward svc/argocd-server -n argocd 8080:443
# Open https://localhost:8080
# Login: admin / <password from above>
```

### ArgoCD CLI

```bash
# Install CLI
brew install argocd

# Login
argocd login localhost:8080 --username admin --password <password>

# Create application
argocd app create doctor-backend-staging \
  --repo https://github.com/your-org/ai-doctor-assistant.git \
  --path infra/k8s/overlays/staging \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace doctor-app

# List applications
argocd app list

# Get application status
argocd app get doctor-backend-staging

# Sync application (apply Git changes to cluster)
argocd app sync doctor-backend-staging

# View sync history
argocd app history doctor-backend-staging

# Rollback to previous version
argocd app rollback doctor-backend-staging <revision>
```

### When to Add ArgoCD

**Start without ArgoCD:** Manual `kubectl apply` or CI/CD pipelines.

**Add ArgoCD when:**
- You have multiple environments (dev, staging, prod)
- Manual deployments become error-prone
- You want audit trail of who deployed what and when
- You need automated rollback (revert Git commit = rollback)

**AI Doctor Assistant approach:**
- **Phase 1 (V1, V2):** GitHub Actions + `kubectl apply` (simpler, faster iteration)
- **Phase 2 (V3+):** ArgoCD for staging + prod (after deployment workflow stabilizes)

---

## Tool Comparison Table

| Tool | Category | Problem Solved | When to Use | AI Doctor Usage |
|------|----------|----------------|-------------|-----------------|
| **gcloud** | GCP Management | Create/manage GCP resources (clusters, registries, IAM, projects) | Creating GKE clusters, pushing images to Artifact Registry, IAM setup | Provision GKE cluster, create Artifact Registry, configure IAM for CI/CD |
| **kubectl** | K8s Client | Interact with Kubernetes API (deploy, debug, view resources) | All K8s operations: apply manifests, view pods, exec into containers, port-forward | Primary tool for deploying/debugging, CI/CD pipelines run kubectl apply |
| **k9s** | K8s Terminal UI | Interactive cluster exploration and debugging | Quick debugging sessions, exploring cluster state, watching logs | Dev debugging, viewing pod status, tailing logs, port-forwarding |
| **Helm** | K8s Package Manager | Install/manage complex third-party apps with reusable charts | Installing PostgreSQL, ArgoCD, ingress-nginx, cert-manager (third-party software) | Install PostgreSQL (Bitnami chart), install ArgoCD (V3+), nginx-ingress (V3+) |
| **Kustomize** | K8s YAML Customization | Customize manifests per environment without templating | Our own app manifests (backend, frontend), environment-specific configs | Base manifests + dev/staging/prod overlays for backend/frontend deployments |
| **ArgoCD** | GitOps CD | Continuously sync cluster state with Git repo (declarative deployments) | Automated deployments, multi-environment management, audit trail | V3+ for staging/prod auto-deployment, rollback via Git revert |
| **Docker/Buildx** | Container Build | Build multi-platform container images | Building backend/frontend images locally and in CI/CD | CI builds amd64/arm64 images, pushes to Artifact Registry |
| **GitHub Actions** | CI/CD | Automate build/test/deploy workflows on Git events | Running tests, building images, deploying to K8s (push-based or trigger ArgoCD) | Run pytest/vitest, build images, push to registry, kubectl apply (V1-V2), trigger ArgoCD sync (V3+) |

---

## Installation Commands

### macOS (Homebrew)

```bash
# Google Cloud SDK (gcloud, gsutil, bq)
brew install google-cloud-sdk

# kubectl (Kubernetes CLI)
brew install kubectl

# k9s (Terminal UI for K8s)
brew install k9s

# Helm (K8s package manager)
brew install helm

# Kustomize (optional, built into kubectl 1.14+)
brew install kustomize

# ArgoCD CLI
brew install argocd

# Docker (for local image builds)
brew install --cask docker
```

### Linux

```bash
# Google Cloud SDK
curl https://sdk.cloud.google.com | bash
exec -l $SHELL  # restart shell

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# k9s
curl -sS https://webi.sh/k9s | sh

# Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Kustomize
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
sudo mv kustomize /usr/local/bin/

# ArgoCD CLI
curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
chmod +x argocd
sudo mv argocd /usr/local/bin/
```

### Verification

```bash
gcloud version
kubectl version --client
k9s version
helm version
kustomize version
argocd version

# Authenticate gcloud
gcloud auth login
gcloud config set project doctor-assistant-prod

# Get GKE credentials (populates kubeconfig)
gcloud container clusters get-credentials doctor-cluster \
  --region=us-central1 \
  --project=doctor-assistant-prod

# Verify kubectl can reach cluster
kubectl cluster-info
kubectl get nodes
```

---

## Putting It All Together: Complete Workflow

### Local Development

```bash
# 1. Write code (IDE)
# 2. Test locally
cd backend && uv run pytest
cd frontend && npm test

# 3. Build images locally
docker build -t backend:local backend/
docker build -t frontend:local frontend/

# 4. Test in local K8s (optional: Minikube/kind)
kubectl apply -k infra/k8s/overlays/dev/
```

### CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/deploy-staging.yml
name: Deploy to Staging

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Authenticate to GCP
        uses: google-github-actions/auth@v1
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - name: Set up gcloud
        uses: google-github-actions/setup-gcloud@v1

      - name: Configure Docker for Artifact Registry
        run: gcloud auth configure-docker us-central1-docker.pkg.dev

      - name: Build and push backend image
        run: |
          docker build -t us-central1-docker.pkg.dev/doctor-assistant-staging/docker-repo/backend:${{ github.sha }} backend/
          docker push us-central1-docker.pkg.dev/doctor-assistant-staging/docker-repo/backend:${{ github.sha }}

      - name: Get GKE credentials
        run: |
          gcloud container clusters get-credentials doctor-cluster \
            --region=us-central1 \
            --project=doctor-assistant-staging

      - name: Deploy to staging
        run: |
          cd infra/k8s/overlays/staging
          kustomize edit set image backend=us-central1-docker.pkg.dev/doctor-assistant-staging/docker-repo/backend:${{ github.sha }}
          kubectl apply -k .

      - name: Verify deployment
        run: kubectl rollout status deployment/doctor-backend -n doctor-app
```

### Production Deployment (with ArgoCD)

```bash
# 1. CI builds and pushes image (same as staging)

# 2. Update Kustomize overlay with new image tag
cd infra/k8s/overlays/prod
kustomize edit set image backend=us-central1-docker.pkg.dev/doctor-assistant-prod/docker-repo/backend:v1.3.0

# 3. Commit and push to Git
git add kustomization.yaml
git commit -m "chore: deploy backend v1.3.0 to prod"
git push origin main

# 4. ArgoCD detects change (automatically or via webhook)
# 5. ArgoCD syncs cluster (applies new manifests)
# 6. View sync status in ArgoCD UI or CLI
argocd app get doctor-backend-prod
```

### Debugging in Production

```bash
# Option 1: kubectl
kubectl get pods -n doctor-app
kubectl logs doctor-backend-7d8f5c9-xkzqp -n doctor-app --tail=100

# Option 2: k9s (faster)
k9s -n doctor-app
# Press ':pods', arrow-key to pod, press 'l' for logs

# Option 3: GCP Console
# Cloud Console → Kubernetes Engine → Workloads → doctor-backend → Logs
```

---

## Summary: Which Tool When?

- **Creating cluster, managing GCP resources:** `gcloud`
- **Deploying, updating, debugging K8s resources:** `kubectl`
- **Interactive debugging, watching logs, exploring:** `k9s`
- **Installing third-party software (PostgreSQL, ArgoCD):** `Helm`
- **Managing own app manifests (backend, frontend):** `Kustomize`
- **Automating deployments, GitOps workflow:** `ArgoCD` (V3+)
- **Building container images:** `Docker`/`buildx`
- **Automating CI/CD:** `GitHub Actions`

**Golden rule:** Use the right tool for the job. Don't force kubectl to manage GCP resources, don't use Helm for your own app manifests, don't use ArgoCD for local debugging.

---

## Next Document

**05-WORKLOAD-TYPES.md** will cover K8s workload types (Pod, Deployment, StatefulSet, DaemonSet, Job, CronJob), when to use each, and how they apply to the AI Doctor Assistant backend, frontend, and PostgreSQL.
