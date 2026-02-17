# Local Kubernetes Development & Infrastructure as Code

> **Document 09 of 11** in the [Infrastructure & Kubernetes Learning Guide](./00-OVERVIEW.md)
>
> **Purpose:** Cover the two remaining pieces of the deployment puzzle -- running Kubernetes locally for manifest validation and testing, and provisioning cloud infrastructure with code rather than manual console clicks. These topics sit at opposite ends of the pipeline but share a common theme: reproducibility.
>
> **Prerequisites:** Documents 01-06 (core K8s concepts, GKE, tooling, app mapping, CI/CD). You should already be comfortable with Deployments, Services, Kustomize overlays, and the AI Doctor Assistant's architecture (FastAPI backend + React frontend + PostgreSQL on GKE Autopilot).

---

## Table of Contents

### Part 1: Local Kubernetes Development
1. [Why Run Kubernetes Locally?](#1-why-run-kubernetes-locally)
2. [Local K8s Cluster Options -- Detailed Comparison](#2-local-k8s-cluster-options--detailed-comparison)
3. [Recommended Setup for AI Doctor Assistant](#3-recommended-setup-for-ai-doctor-assistant)
4. [Skaffold -- Hot Reload for Kubernetes](#4-skaffold--hot-reload-for-kubernetes)
5. [Tilt -- Alternative to Skaffold](#5-tilt--alternative-to-skaffold)
6. [The Full Local Dev Workflow](#6-the-full-local-dev-workflow)

### Part 2: Infrastructure as Code (IaC)
7. [What is IaC and Why Does It Matter?](#7-what-is-iac-and-why-does-it-matter)
8. [IaC Tool Landscape -- Detailed Comparison](#8-iac-tool-landscape--detailed-comparison)
9. [Comprehensive Comparison Table](#9-comprehensive-comparison-table)
10. [Terraform vs Pulumi -- Deep Dive](#10-terraform-vs-pulumi--deep-dive)
11. [Recommended Approach for AI Doctor Assistant](#11-recommended-approach-for-ai-doctor-assistant)
12. [How IaC and K8s Tools Fit Together](#12-how-iac-and-k8s-tools-fit-together)

---

# Part 1: Local Kubernetes Development

---

## 1. Why Run Kubernetes Locally?

You already have `docker-compose up` and it works. The backend starts with uvicorn hot reload, the frontend runs `vite dev`, PostgreSQL comes up in a container, and you write code against `localhost`. Why would you add Kubernetes to your local workflow?

The answer is that docker-compose and local Kubernetes serve **different purposes** and you should use both.

**docker-compose is for daily development.** It starts your services fast, supports hot reload, and has zero Kubernetes concepts to think about. When you are writing a new FastAPI endpoint or adjusting a React component, docker-compose is the right tool. You should not replace it with Kubernetes for everyday coding.

**Local Kubernetes is for manifest validation.** Before pushing Kustomize overlays to GKE, you want to know that they actually work. Does the health probe path match the endpoint your backend exposes? Are the resource requests reasonable or will the Pod get OOMKilled? Does service discovery resolve correctly between the backend and PostgreSQL? These are questions that docker-compose cannot answer because docker-compose does not use Kubernetes manifests at all.

Here is what local Kubernetes catches that docker-compose cannot:

- **Manifest syntax errors.** A missing field in a Deployment spec, a typo in a label selector, an incorrect port number in a Service definition. `kubectl apply` will fail locally before you waste a CI/CD cycle pushing broken manifests to GKE.

- **Kustomize overlay correctness.** Your base manifests might be valid, but when Kustomize patches the dev overlay on top, does the result make sense? Local testing lets you run `kubectl apply -k overlays/dev/` and see the actual merged output.

- **Health probe behavior.** If your readiness probe hits `/health` but your FastAPI app exposes `/api/health`, the Pod will never become ready. This is trivial to catch locally and painful to debug in a cloud cluster where you are also fighting IAM permissions and network policies.

- **Resource limit tuning.** Setting `memory: 128Mi` on a Python process that needs 256Mi at startup means the OOM killer will terminate it. Locally, you can observe this behavior and adjust limits before it affects a production deployment.

- **Service discovery and DNS.** Your backend connects to PostgreSQL at `postgres.doctor-app.svc.cluster.local`. This DNS name only exists inside a Kubernetes cluster. docker-compose uses its own DNS (`postgres` as a hostname), which does not test the real K8s service resolution.

The mental model is simple: **"if it works on minikube, it works on GKE."** The Kubernetes API is the same. The manifests are the same. The differences are in the underlying infrastructure (a single-node VM versus a multi-node cloud cluster), not in how Kubernetes interprets your YAML files.

> **AI Doctor Example:** The AI Doctor Assistant uses Kustomize overlays for dev, staging, and production. Before pushing changes to the `infra/k8s/overlays/dev/` directory, you run `kubectl apply -k infra/k8s/overlays/dev/` against a local minikube cluster. If the backend Pod starts, passes its health check, and the frontend can reach it through the Service, you know the manifests are correct. This takes 2-3 minutes and saves you from a broken deployment on GKE that could take 10-15 minutes to debug.

---

## 2. Local K8s Cluster Options -- Detailed Comparison

There are several tools that create Kubernetes clusters on your local machine. Each makes different tradeoffs around resource usage, feature completeness, and how closely the cluster resembles a real cloud environment. Here is a thorough breakdown.

### 2.1 minikube

**What it is:** The most popular local Kubernetes tool, originally created by the Kubernetes community and backed by Google. It runs a single-node Kubernetes cluster on your machine.

**How it works:** minikube creates a virtual machine (or Docker container, depending on the driver) and installs a full Kubernetes distribution inside it. The VM runs the control plane components (API server, etcd, scheduler, controller manager) and also acts as the single worker node. It supports multiple drivers: Docker (recommended), HyperKit (macOS), VirtualBox, and others.

**Install and usage:**

```bash
# Install on macOS
brew install minikube

# Create a cluster (Docker driver is fastest)
minikube start --memory=4096 --cpus=2 --driver=docker

# Stop the cluster (preserves state)
minikube stop

# Delete the cluster entirely
minikube delete

# Load a local Docker image into minikube (skip registry push)
minikube image load my-app:dev

# Expose LoadBalancer services to localhost
minikube tunnel

# Open the Kubernetes dashboard
minikube dashboard
```

**Addons system:** minikube includes a built-in addon manager for common cluster components. This is one of its strongest features.

```bash
# List all available addons
minikube addons list

# Enable useful addons
minikube addons enable ingress           # NGINX Ingress Controller
minikube addons enable metrics-server    # Resource metrics (for HPA)
minikube addons enable dashboard         # Web UI
minikube addons enable registry          # Local container registry
```

**Resource usage:** 2-4 GB RAM, 2 CPUs recommended. With the Docker driver, overhead is lower than with a full VM.

**Pros:**
- Most feature-rich local K8s tool
- Addon ecosystem covers most needs (ingress, metrics, dashboard, GPU passthrough)
- `minikube tunnel` provides real LoadBalancer IP addresses
- `minikube image load` skips the need for a registry
- Closest behavior to GKE of any local option
- Excellent documentation and community support

**Cons:**
- Slower startup than kind or k3d (60-90 seconds vs 30 seconds)
- Heavier resource usage than container-based alternatives
- Single-node only (cannot test multi-node scenarios like node affinity)

**Best for:** Learning Kubernetes, validating manifests for GKE deployment, local development with full-fidelity K8s behavior.

---

### 2.2 kind (Kubernetes IN Docker)

**What it is:** kind runs Kubernetes cluster nodes as Docker containers rather than virtual machines. Each "node" is a Docker container running the Kubernetes control plane or kubelet. It was originally built by the Kubernetes project for its own CI testing.

**How it works:** kind uses `kubeadm` to bootstrap a Kubernetes cluster inside Docker containers. When you ask for a multi-node cluster, kind creates multiple Docker containers -- one for the control plane and one for each worker node. These containers communicate over a Docker network, simulating a real multi-node cluster. Because containers are lighter than VMs, kind starts significantly faster.

**Install and usage:**

```bash
# Install on macOS
brew install kind

# Create a cluster with default settings (single node)
kind create cluster --name doctor-dev

# Create a multi-node cluster with a config file
cat <<EOF | kind create cluster --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
- role: worker
- role: worker
EOF

# Delete the cluster
kind delete cluster --name doctor-dev

# Load a local Docker image into the cluster
kind load docker-image my-app:dev --name doctor-dev
```

**Resource usage:** 1-2 GB RAM for a single-node cluster. Multi-node clusters add roughly 500MB per additional node.

**Pros:**
- Extremely fast startup (20-30 seconds)
- Multi-node clusters (test node affinity, pod anti-affinity, taints/tolerations)
- Lightweight (Docker containers, not VMs)
- Used by the Kubernetes project itself for upstream testing
- Excellent for CI/CD pipelines (fast, disposable, scriptable)
- Supports loading local images without a registry

**Cons:**
- No built-in addon manager (must manually install ingress controller, metrics server)
- No equivalent of `minikube tunnel` for LoadBalancer services out of the box
- Ingress setup requires extra config (port mappings in the kind config file)
- Less polished developer experience than minikube for interactive use

**Best for:** CI/CD pipelines (GitHub Actions), fast iteration when you know what you are doing, testing multi-node scenarios.

---

### 2.3 k3d (k3s in Docker)

**What it is:** k3d runs k3s -- a lightweight Kubernetes distribution created by Rancher Labs -- inside Docker containers. k3s strips out features that most users do not need (cloud provider integrations, legacy APIs, in-tree storage drivers) to create a smaller, faster Kubernetes binary.

**How it works:** k3d creates Docker containers running k3s instead of full Kubernetes. The k3s binary is a single ~50MB file that contains the API server, scheduler, controller manager, and kubelet all in one. This makes startup extremely fast and resource usage minimal.

**Install and usage:**

```bash
# Install on macOS
brew install k3d

# Create a cluster
k3d cluster create doctor-dev --agents 2

# Delete a cluster
k3d cluster delete doctor-dev

# Import a local image
k3d image import my-app:dev -c doctor-dev
```

**Resource usage:** 512MB-1GB RAM. The smallest footprint of any local K8s option.

**Pros:**
- Fastest startup (10-20 seconds)
- Smallest resource footprint
- Multi-node support
- Built-in Traefik ingress controller (k3s default)
- Built-in local registry support
- Excellent for resource-constrained machines

**Cons:**
- Not full Kubernetes (some CRDs and APIs may behave differently)
- Fewer community resources and examples compared to minikube or kind
- k3s-specific defaults may not match GKE behavior (e.g., Traefik vs NGINX ingress)
- Edge cases where k3s and full K8s diverge can create surprises

**Best for:** Resource-constrained machines, quick tests, scenarios where you need multiple clusters simultaneously.

---

### 2.4 Docker Desktop Kubernetes

**What it is:** Docker Desktop (the GUI application for Mac and Windows) includes a built-in Kubernetes option. You enable it by checking a box in Settings > Kubernetes.

**How it works:** Docker Desktop runs a single-node Kubernetes cluster alongside its Docker daemon. It shares the same Docker runtime, so images you build locally are automatically available to the cluster without any `image load` step.

**Install and usage:**

```bash
# No separate install -- enable in Docker Desktop Settings > Kubernetes

# kubectl context is set automatically
kubectl config use-context docker-desktop

# No explicit create/delete -- toggling the checkbox starts/stops the cluster
```

**Resource usage:** 2-4 GB RAM (shared with Docker Desktop's overall allocation).

**Pros:**
- Zero install steps (already comes with Docker Desktop)
- Images built locally are immediately available to the cluster
- Simplest possible setup for beginners

**Cons:**
- No addon manager, no dashboard, no ingress controller out of the box
- Cannot customize Kubernetes version (uses whatever Docker Desktop ships)
- Heavy resource usage (Docker Desktop itself is already resource-hungry)
- No multi-node support
- Cannot be used in CI/CD (no headless/CLI-only mode)
- Docker Desktop licensing: free for personal/small business, paid for larger companies

**Best for:** Developers who just want Kubernetes to work without thinking about cluster management. Not recommended for serious development or CI.

---

### 2.5 Rancher Desktop

**What it is:** An open-source, free alternative to Docker Desktop that includes a Kubernetes cluster based on k3s. Developed by SUSE/Rancher.

**How it works:** Rancher Desktop installs a k3s-based Kubernetes cluster and provides either containerd or dockerd as the container runtime. It includes a GUI for managing the cluster version and settings.

**Resource usage:** 2-3 GB RAM.

**Pros:**
- Free and open source (no licensing concerns)
- Choose your Kubernetes version
- Choose between containerd and dockerd
- Built-in Traefik ingress

**Cons:**
- Less mature than Docker Desktop or minikube
- k3s-based (same caveats as k3d regarding full K8s compatibility)
- Smaller community

**Best for:** Developers who want to avoid Docker Desktop's licensing model and need a graphical cluster management tool.

---

### 2.6 Comparison Table

| Feature | minikube | kind | k3d | Docker Desktop |
|---|---|---|---|---|
| **Install** | `brew install minikube` | `brew install kind` | `brew install k3d` | GUI checkbox |
| **Startup time** | 60-90 seconds | 20-30 seconds | 10-20 seconds | 30-60 seconds |
| **RAM usage** | 2-4 GB | 1-2 GB | 512MB-1 GB | 2-4 GB |
| **Multi-node** | No | Yes | Yes | No |
| **Ingress support** | Addon (one command) | Manual install | Built-in (Traefik) | Manual install |
| **LoadBalancer support** | `minikube tunnel` | Extra setup needed | Port mapping | Limited |
| **Image loading** | `minikube image load` | `kind load docker-image` | `k3d image import` | Automatic |
| **Dashboard** | Addon (one command) | Manual install | Manual install | No |
| **GPU passthrough** | Yes (with drivers) | No | No | No |
| **CI/CD friendly** | Possible but slow | Excellent | Excellent | No |
| **Closest to GKE** | Yes | Close | Less (k3s diffs) | Close |
| **Addon manager** | Built-in (40+ addons) | None | None | None |

---

## 3. Recommended Setup for AI Doctor Assistant

For the AI Doctor Assistant project, the recommendation is:

- **minikube** for local development and learning (closest to GKE, best addon support, excellent for validating manifests before cloud deployment)
- **kind** for CI testing in GitHub Actions (fast startup, disposable, purpose-built for CI)

You do not need both installed on your dev machine. Start with minikube. If you later set up GitHub Actions to run K8s integration tests, use kind in those workflows.

### Full Walkthrough with minikube

Here is the complete workflow for testing AI Doctor manifests locally:

```bash
# -----------------------------------------------
# Step 1: Install minikube (one time)
# -----------------------------------------------
brew install minikube

# -----------------------------------------------
# Step 2: Create a cluster with enough resources
# -----------------------------------------------
# AI Doctor needs:
#   - Backend: ~256Mi RAM, 250m CPU
#   - Frontend: ~128Mi RAM, 100m CPU
#   - PostgreSQL: ~256Mi RAM, 250m CPU
#   - K8s system components: ~1GB RAM
# Total: ~2GB minimum. Set 4GB for headroom.

minikube start \
  --memory=4096 \
  --cpus=2 \
  --driver=docker \
  --kubernetes-version=v1.29.0

# -----------------------------------------------
# Step 3: Enable addons that match your GKE setup
# -----------------------------------------------
minikube addons enable ingress          # NGINX Ingress Controller
minikube addons enable metrics-server   # Needed for HPA testing

# -----------------------------------------------
# Step 4: Build container images locally
# -----------------------------------------------
docker build -t doctor-backend:dev backend/
docker build -t doctor-frontend:dev frontend/

# -----------------------------------------------
# Step 5: Load images into minikube
# -----------------------------------------------
# This copies the images from your local Docker daemon
# into minikube's internal image store. No registry needed.
minikube image load doctor-backend:dev
minikube image load doctor-frontend:dev

# -----------------------------------------------
# Step 6: Deploy with Kustomize
# -----------------------------------------------
# Use the SAME overlays you would deploy to GKE.
# This is the whole point of local K8s testing.
kubectl apply -k infra/k8s/overlays/dev/

# -----------------------------------------------
# Step 7: Verify everything is running
# -----------------------------------------------
kubectl get pods -n doctor-app
kubectl get services -n doctor-app
kubectl get ingress -n doctor-app

# Check logs if a pod is not starting
kubectl logs -n doctor-app deployment/doctor-backend
kubectl describe pod -n doctor-app -l app=doctor-backend

# -----------------------------------------------
# Step 8: Access the application
# -----------------------------------------------

# Option A: Port forward (simplest, works immediately)
kubectl port-forward svc/doctor-frontend 8080:80 -n doctor-app
# Open http://localhost:8080

# Option B: minikube tunnel (for Ingress/LoadBalancer)
# Run in a separate terminal -- it stays running
minikube tunnel
# Open the Ingress IP shown in: kubectl get ingress -n doctor-app

# -----------------------------------------------
# Step 9: Test health probes
# -----------------------------------------------
# Exec into a running pod and curl the health endpoint
kubectl exec -it -n doctor-app deployment/doctor-backend -- curl localhost:8000/health

# -----------------------------------------------
# Step 10: Clean up when done
# -----------------------------------------------
kubectl delete -k infra/k8s/overlays/dev/
minikube stop      # preserves cluster state
# or
minikube delete    # destroys cluster entirely
```

### Important: imagePullPolicy for Local Images

When using locally loaded images (not pulled from a registry), your Deployment manifests need `imagePullPolicy: Never` or `imagePullPolicy: IfNotPresent`. Otherwise Kubernetes will try to pull the image from a remote registry and fail.

Your Kustomize dev overlay should patch this:

```yaml
# infra/k8s/overlays/dev/kustomization.yaml
patches:
- target:
    kind: Deployment
  patch: |-
    - op: replace
      path: /spec/template/spec/containers/0/imagePullPolicy
      value: IfNotPresent
```

---

## 4. Skaffold -- Hot Reload for Kubernetes

### What Problem Does Skaffold Solve?

The workflow in Section 3 has a friction point: every time you change code, you must manually rebuild the Docker image, reload it into minikube, and re-apply the Kubernetes manifests. For a single test cycle this is fine. For iterative development, it is tedious.

Skaffold automates this entire cycle. Created by Google, it watches your source files, detects changes, rebuilds the affected container images, loads them into the cluster, and re-applies the manifests. The experience is similar to how `vite dev` watches your TypeScript files and hot-reloads the browser -- except Skaffold does it for Kubernetes deployments.

**Key point:** Skaffold is not a cluster tool. It does not create or manage Kubernetes clusters. It needs a cluster to already exist (minikube, kind, GKE, or anything else with a valid kubeconfig). Skaffold sits on top of the cluster and automates the build-push-deploy loop.

### Install

```bash
brew install skaffold
```

### skaffold.yaml for AI Doctor Assistant

```yaml
apiVersion: skaffold/v4beta6
kind: Config
metadata:
  name: doctor-app

build:
  artifacts:
  - image: doctor-backend
    context: backend
    docker:
      dockerfile: Dockerfile
    sync:
      # Sync Python files without full rebuild (fast feedback)
      manual:
      - src: "src/**/*.py"
        dest: /app
  - image: doctor-frontend
    context: frontend
    docker:
      dockerfile: Dockerfile
  local:
    push: false              # Load images directly into minikube (no registry)
    useBuildkit: true         # Faster builds with BuildKit

deploy:
  kustomize:
    paths:
    - infra/k8s/overlays/dev

portForward:
  - resourceType: service
    resourceName: doctor-frontend
    namespace: doctor-app
    port: 80
    localPort: 8080
  - resourceType: service
    resourceName: doctor-backend
    namespace: doctor-app
    port: 8000
    localPort: 8000
```

### Usage

```bash
# -----------------------------------------------
# Watch mode: rebuild and redeploy on every code change
# -----------------------------------------------
skaffold dev

# What happens:
# 1. Skaffold builds doctor-backend and doctor-frontend images
# 2. Loads them into minikube (push: false)
# 3. Runs kubectl apply -k infra/k8s/overlays/dev
# 4. Sets up port forwarding (localhost:8080 -> frontend, localhost:8000 -> backend)
# 5. Watches for file changes
# 6. On change: rebuilds affected image, redeploys
# 7. Ctrl+C: tears down all deployed resources

# -----------------------------------------------
# One-shot: build and deploy once, then exit
# -----------------------------------------------
skaffold run

# -----------------------------------------------
# Debug mode: like dev but attaches debugger
# -----------------------------------------------
skaffold debug

# -----------------------------------------------
# Tear down everything Skaffold deployed
# -----------------------------------------------
skaffold delete
```

### When to Use Skaffold vs docker-compose

| Scenario | docker-compose | Skaffold + minikube |
|---|---|---|
| Daily backend/frontend coding | Use this | Overkill |
| Testing K8s manifests work | Cannot do this | Use this |
| Testing health probes and resource limits | Cannot do this | Use this |
| CI pipeline K8s validation | Not applicable | Use this (or kind) |
| Pre-deploy validation before pushing to GKE | Cannot do this | Use this |
| Debugging Python/React code with hot reload | Faster here | Slower feedback loop |
| Testing Ingress routing rules | Cannot do this | Use this |
| Onboarding a new developer | Simpler starting point | Introduce after basics |

The rule of thumb: if you are changing application code, use docker-compose. If you are changing anything related to Kubernetes deployment (manifests, Dockerfiles, resource limits, probes, ingress rules), switch to Skaffold with minikube.

---

## 5. Tilt -- Alternative to Skaffold

Tilt solves the same problem as Skaffold (watch source code, rebuild, redeploy to K8s) but takes a different approach. Where Skaffold uses a declarative YAML config, Tilt uses a `Tiltfile` written in Starlark (a Python-like language). Tilt also provides a web-based dashboard that shows the status of all your services, their logs, and build times in one place.

### Tiltfile for AI Doctor Assistant

```python
# Tiltfile

# Build images
docker_build('doctor-backend', './backend')
docker_build('doctor-frontend', './frontend')

# Deploy with Kustomize
k8s_yaml(kustomize('infra/k8s/overlays/dev'))

# Configure port forwards
k8s_resource('doctor-backend', port_forwards='8000:8000')
k8s_resource('doctor-frontend', port_forwards='8080:80')

# Live update: sync files without full rebuild
docker_build(
    'doctor-backend',
    './backend',
    live_update=[
        sync('./backend/src', '/app/src'),
        run('cd /app && uv sync', trigger=['./backend/pyproject.toml']),
    ]
)
```

### Usage

```bash
# Install
brew install tilt

# Start (opens web dashboard automatically)
tilt up

# Tear down
tilt down
```

### Skaffold vs Tilt

| Aspect | Skaffold | Tilt |
|---|---|---|
| Config language | YAML | Starlark (Python-like) |
| Dashboard | CLI output only | Web UI (excellent) |
| Live update | File sync supported | First-class feature |
| Backed by | Google | Docker (acquired 2022) |
| Maturity | Older, more stable | Newer, growing fast |
| CI/CD use | Common (`skaffold run`) | Possible but less common |
| Learning curve | Low (just YAML) | Medium (new language) |
| Extensibility | Limited | Starlark is programmable |

**Recommendation for AI Doctor:** Start with Skaffold. It uses YAML you already understand, integrates naturally with Kustomize (which you already use), and was built by Google to work well with GKE. If you later want a better dashboard experience, try Tilt. Both tools are good choices -- this is not a critical decision.

---

## 6. The Full Local Dev Workflow

Here is how all the tools fit together in your daily and weekly workflow:

```
Daily Development (most of your time)         Pre-Deploy Validation (before merging K8s changes)
====================================          ===================================================

docker-compose up                             minikube start
  |                                             |
  v                                             v
Backend: uvicorn --reload (port 8000)         docker build -t doctor-backend:dev backend/
Frontend: vite dev server (port 5173)         docker build -t doctor-frontend:dev frontend/
PostgreSQL: container (port 5432)               |
  |                                             v
  v                                           minikube image load doctor-backend:dev
Write code, save, see changes instantly       minikube image load doctor-frontend:dev
  |                                             |
  v                                             v
Run tests:                                    kubectl apply -k infra/k8s/overlays/dev/
  cd backend && uv run pytest                   |
  cd frontend && npm test                       v
  |                                           Verify:
  v                                             kubectl get pods -n doctor-app (all Running?)
Commit, push, repeat                            kubectl logs deployment/doctor-backend -n doctor-app
                                                kubectl port-forward svc/doctor-frontend 8080:80
                                                |
                                                v
                                              Everything works? --> Push to GKE with confidence
                                              Something broken? --> Fix manifests, re-apply, iterate
```

The key insight: these are **two separate workflows** for two separate concerns. You switch between them based on what you are changing, not based on personal preference. Code changes go through docker-compose. Infrastructure changes go through minikube.

If you find yourself frequently switching between the two (e.g., changing code AND manifests in the same PR), that is when Skaffold earns its place -- it bridges both workflows by watching code files and re-deploying to a running minikube cluster automatically.

---

# Part 2: Infrastructure as Code (IaC)

---

## 7. What is IaC and Why Does It Matter?

Infrastructure as Code means defining your cloud resources -- clusters, databases, registries, IAM roles, DNS records, VPCs -- in code files that live in your git repository, rather than creating them manually through a cloud console or ad-hoc CLI commands.

### The Problem IaC Solves

Without IaC, your infrastructure exists only in the cloud provider's state. If someone asks "how was our GKE cluster configured?", the answer is "log into the GCP console and look." If the cluster is accidentally deleted, you have to remember every setting, every IAM binding, every network configuration, and recreate it manually. If you want a second environment (staging), you repeat every manual step and hope you do not miss anything.

With IaC, the answer to "how is our cluster configured?" is "read the code in `infra/pulumi/` or `infra/terraform/`." If the cluster is deleted, you run `pulumi up` or `terraform apply` and everything is recreated exactly as it was. If you want a staging environment, you parameterize the code and deploy it with different variables.

### The Core Benefits

**Version controlled.** Infrastructure changes go through pull requests, get reviewed by teammates, and have a full git history. You can answer "who changed the cluster config last Thursday and why?" by looking at the git log.

**Reproducible.** "I can destroy everything and recreate it in 5 minutes" is not an exaggeration. IaC tools track the state of your infrastructure and can recreate it from scratch.

**Reviewable.** Before applying a change, IaC tools show you a plan: "I will create 2 resources, modify 1, and destroy 0." This is like a `git diff` for infrastructure. You review the plan, approve it, and then the tool applies the changes.

**Self-documenting.** The code IS the documentation. Instead of a wiki page that says "we use a GKE Autopilot cluster in us-central1 with Workload Identity enabled," the Terraform or Pulumi code describes this precisely, and unlike documentation, it cannot become outdated because it is the actual source of truth.

### Imperative vs Declarative

There are two approaches to IaC:

**Imperative: "Run these commands in this order."** This is what a shell script does. You write `gcloud container clusters create-auto doctor-cluster --region=us-central1` and run it. The problem: if you run it again, it fails because the cluster already exists. You need to add `if not exists` logic, handle partial failures, and manage ordering dependencies yourself. The script describes *how* to build infrastructure, not *what* the infrastructure should look like.

**Declarative: "This is what I want to exist."** This is what Terraform and Pulumi do. You declare "a GKE Autopilot cluster named doctor-cluster should exist in us-central1." The tool figures out what needs to happen: if the cluster does not exist, create it. If it exists but the config differs, update it. If it exists and matches, do nothing. The declaration describes *what* the infrastructure should look like, and the tool handles the *how*.

Declarative is strictly better for anything beyond trivial setups. The tradeoff is that declarative tools require learning a new system (state management, providers, modules), while imperative scripts use tools you already know (bash, gcloud).

---

## 8. IaC Tool Landscape -- Detailed Comparison

### 8.1 gcloud CLI Scripts

The simplest form of infrastructure automation: a shell script that runs gcloud commands in sequence.

```bash
#!/bin/bash
# infra/gcp/setup-cluster.sh
#
# Provision all GCP resources for AI Doctor Assistant.
# Run once to set up, then never touch again (hopefully).

set -euo pipefail

PROJECT_ID="doctor-assistant-prod"
REGION="us-central1"
CLUSTER_NAME="doctor-cluster"
REPO_NAME="doctor-app"

echo "==> Setting project..."
gcloud config set project "$PROJECT_ID"

echo "==> Enabling required APIs..."
gcloud services enable container.googleapis.com
gcloud services enable artifactregistry.googleapis.com

echo "==> Creating GKE Autopilot cluster..."
gcloud container clusters create-auto "$CLUSTER_NAME" \
  --region="$REGION" \
  --release-channel=regular

echo "==> Creating Artifact Registry repository..."
gcloud artifacts repositories create "$REPO_NAME" \
  --repository-format=docker \
  --location="$REGION" \
  --description="AI Doctor container images"

echo "==> Creating service account for GitHub Actions..."
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions Deployer"

echo "==> Done. Cluster and registry are ready."
```

**Language:** Bash
**State management:** None. The script does not track what exists. Re-running it will fail on resources that already exist.
**Strengths:** Zero learning curve, uses tools you already know, good for small setups.
**Weaknesses:** No state, no plan/preview, no drift detection, fragile to re-runs, ordering dependencies are manual.
**When to use:** Initial setup of a small project. Prototyping. Learning GCP APIs before switching to a real IaC tool.

---

### 8.2 Terraform / OpenTofu

Terraform is the industry standard for IaC. Created by HashiCorp, it uses a domain-specific language called HCL (HashiCorp Configuration Language) to declare infrastructure. In August 2023, HashiCorp changed Terraform's license from open-source (MPL) to the Business Source License (BSL), which restricts commercial use by competitors. In response, the community forked Terraform into **OpenTofu**, which remains fully open-source under the Linux Foundation. OpenTofu is a drop-in replacement -- same syntax, same providers, same commands (replace `terraform` with `tofu`).

```hcl
# infra/terraform/main.tf

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {
    bucket = "doctor-terraform-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# GKE Autopilot Cluster
resource "google_container_cluster" "doctor" {
  name     = "doctor-cluster"
  location = var.region

  enable_autopilot = true

  release_channel {
    channel = "REGULAR"
  }

  # Workload Identity (recommended for GKE)
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
}

# Artifact Registry for container images
resource "google_artifact_registry_repository" "doctor" {
  location      = var.region
  repository_id = "doctor-app"
  format        = "DOCKER"
  description   = "AI Doctor container images"
}

# Service account for GitHub Actions CI/CD
resource "google_service_account" "github_deployer" {
  account_id   = "github-deployer"
  display_name = "GitHub Actions Deployer"
}

# Grant deployer permission to push images
resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  location   = google_artifact_registry_repository.doctor.location
  repository = google_artifact_registry_repository.doctor.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_deployer.email}"
}

# Grant deployer permission to deploy to GKE
resource "google_project_iam_member" "deployer_gke" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}
```

```hcl
# infra/terraform/variables.tf

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}
```

**Usage:**

```bash
# Initialize (download providers, configure backend)
terraform init

# Preview changes (what will be created/modified/destroyed)
terraform plan

# Apply changes (actually create resources)
terraform apply

# Destroy all resources
terraform destroy
```

**Language:** HCL (HashiCorp Configuration Language) -- a domain-specific language designed for infrastructure declaration.
**State management:** Terraform maintains a state file (`terraform.tfstate`) that records every resource it manages, their current properties, and their dependencies. The state file can be stored locally (for learning) or in a remote backend (GCS bucket, S3, Terraform Cloud) for team collaboration.
**Strengths:** Industry standard (most job postings, most examples online, most community modules), massive provider ecosystem (every cloud, every SaaS), mature tooling, excellent `plan` output.
**Weaknesses:** HCL is a new language to learn, state file management requires care (locking, remote backends, state corruption), conditionals and loops are awkward compared to real programming languages, refactoring resources can require state surgery (`terraform state mv`).
**When to use:** Any serious infrastructure project. This is the default choice unless you have a strong reason to choose something else.

---

### 8.3 Pulumi

Pulumi takes the same declarative-state-managed approach as Terraform but lets you write infrastructure code in real programming languages: TypeScript, Python, Go, C#, Java, and YAML. For a TypeScript developer, this means you get loops, conditionals, async/await, type checking, IDE autocomplete, npm packages, and unit testing with familiar tools -- all applied to infrastructure definition.

```typescript
// infra/pulumi/index.ts

import * as pulumi from "@pulumi/pulumi";
import * as gcp from "@pulumi/gcp";

const config = new pulumi.Config();
const projectId = config.require("projectId");
const region = config.get("region") || "us-central1";

// GKE Autopilot Cluster
const cluster = new gcp.container.Cluster("doctor-cluster", {
  location: region,
  enableAutopilot: true,
  releaseChannel: {
    channel: "REGULAR",
  },
  workloadIdentityConfig: {
    workloadPool: `${projectId}.svc.id.goog`,
  },
});

// Artifact Registry for container images
const registry = new gcp.artifactregistry.Repository("doctor-app", {
  location: region,
  format: "DOCKER",
  description: "AI Doctor container images",
});

// Service account for GitHub Actions CI/CD
const deployer = new gcp.serviceaccount.Account("github-deployer", {
  accountId: "github-deployer",
  displayName: "GitHub Actions Deployer",
});

// Grant deployer permission to push images
const deployerPush = new gcp.artifactregistry.RepositoryIamMember("deployer-push", {
  location: registry.location,
  repository: registry.name,
  role: "roles/artifactregistry.writer",
  member: pulumi.interpolate`serviceAccount:${deployer.email}`,
});

// Grant deployer permission to deploy to GKE
const deployerGke = new gcp.projects.IAMMember("deployer-gke", {
  project: projectId,
  role: "roles/container.developer",
  member: pulumi.interpolate`serviceAccount:${deployer.email}`,
});

// Export useful values
export const clusterEndpoint = cluster.endpoint;
export const clusterName = cluster.name;
export const registryUrl = pulumi.interpolate`${region}-docker.pkg.dev/${projectId}/${registry.repositoryId}`;
```

**Usage:**

```bash
# Initialize a new project
pulumi new gcp-typescript

# Preview changes
pulumi preview

# Apply changes
pulumi up

# Destroy all resources
pulumi destroy
```

**Language:** TypeScript, Python, Go, C#, Java, or YAML.
**State management:** Same concept as Terraform -- a state file tracking all managed resources. Default backend is Pulumi Cloud (free tier: unlimited individual use). Can also use self-managed backends: S3, GCS, Azure Blob, or local filesystem.
**Strengths:** Full programming language (loops, conditionals, functions, classes, async/await), excellent IDE support (TypeScript type checking, autocomplete), unit testable with standard test frameworks (Jest, pytest), npm/pip package ecosystem for sharing infrastructure modules, growing rapidly in adoption.
**Weaknesses:** Smaller community than Terraform (fewer examples, fewer Stack Overflow answers), fewer third-party modules, less mature provider coverage for niche services, Pulumi Cloud dependency (optional but default), job market still favors Terraform knowledge.
**When to use:** When your team already knows TypeScript or Python well and wants to avoid learning HCL. When you need complex logic (conditional resource creation, dynamic naming, loops over lists of environments). When you value testability and IDE support.

---

### 8.4 Crossplane

Crossplane is a Kubernetes-native IaC tool. It extends the Kubernetes API with Custom Resource Definitions (CRDs) that represent cloud resources. You create a GKE cluster the same way you create a Deployment -- by applying a YAML manifest to a Kubernetes cluster. Crossplane controllers running inside the cluster watch for these CRDs and provision the actual cloud resources.

```yaml
# crossplane/cluster.yaml
apiVersion: container.gcp.crossplane.io/v1beta1
kind: Cluster
metadata:
  name: doctor-cluster
spec:
  forProvider:
    location: us-central1
    autopilot:
      enabled: true
    releaseChannel:
      channel: REGULAR
  providerConfigRef:
    name: gcp-provider
```

**Language:** Kubernetes YAML (same syntax as Deployments, Services, etc.).
**State management:** Kubernetes itself is the state store (etcd). Crossplane resources are K8s objects with status fields reflecting the cloud resource state.
**Strengths:** Kubernetes-native (one tool for everything), GitOps-compatible (ArgoCD can manage both app manifests AND infra), self-service platforms (teams request resources via K8s manifests without cloud console access).
**Weaknesses:** Chicken-and-egg problem (you need a Kubernetes cluster to run Crossplane, but you might be using Crossplane to create the cluster), steep learning curve (CRDs, compositions, claims), less mature than Terraform, smaller community, debugging is harder (issues can be in the CRD, the provider, or the cloud API).
**When to use:** Platform engineering teams building self-service infrastructure portals. Organizations that want a single control plane (Kubernetes) for both applications and infrastructure. NOT recommended for small teams or initial setups.

---

### 8.5 Other Tools (Brief Mentions)

**AWS CDK / GCP Cloud Deployment Manager:** Provider-specific IaC tools. AWS CDK (Cloud Development Kit) is popular in AWS-only organizations and uses TypeScript/Python (similar to Pulumi but AWS-only). GCP Cloud Deployment Manager exists but is rarely used -- the GCP ecosystem has converged on Terraform. Avoid these unless you are locked into a single cloud provider with no plans to change.

**Ansible:** A configuration management tool, not an IaC tool in the modern sense. Ansible excels at SSHing into machines and installing software, configuring services, and managing operating system state. It CAN provision cloud resources through modules, but it lacks state management, plan/preview, and drift detection. Use Ansible for post-provisioning configuration (e.g., installing agents on VMs), not for creating cloud resources. In a Kubernetes world, Ansible's role is minimal because containers handle their own configuration.

---

## 9. Comprehensive Comparison Table

| Aspect | gcloud CLI | Terraform | Pulumi | Crossplane |
|---|---|---|---|---|
| **Language** | Bash | HCL | TypeScript/Python/Go | Kubernetes YAML |
| **Paradigm** | Imperative | Declarative | Declarative | Declarative |
| **State management** | None | State file (GCS/S3/local) | State file (Pulumi Cloud/GCS/S3) | Kubernetes etcd |
| **Multi-cloud** | GCP only | Yes (any provider) | Yes (any provider) | Yes (any provider) |
| **Learning curve** | Very low | Medium (HCL + state) | Low-medium (if you know TS) | High (CRDs + K8s deep knowledge) |
| **Destroy/recreate** | Manual | `terraform destroy` + `apply` | `pulumi destroy` + `up` | Delete CRD objects |
| **Drift detection** | None | `terraform plan` shows drift | `pulumi preview` shows drift | Continuous reconciliation |
| **IDE support** | Bash highlighting | HCL plugin (decent) | Full TS/Python IDE support | YAML + CRD schemas |
| **Testing** | Shell script tests | `terraform validate`, terratest | Jest, pytest, Go test | K8s manifest validation |
| **Community/jobs** | N/A | Largest (industry standard) | Growing fast | Niche (platform eng) |
| **Cost** | Free | Free (OpenTofu) / BSL (Terraform) | Free tier + paid plans | Free (open source) |
| **AI Doctor fit** | Phase 1 (quick start) | Phase 3 (job prep) | Phase 2 (TS dev experience) | Overkill |

---

## 10. Terraform vs Pulumi -- Deep Dive

Since Terraform and Pulumi are the two main contenders for the AI Doctor Assistant project, here is a detailed head-to-head comparison.

### Feature-by-Feature Comparison

| Aspect | Terraform (HCL) | Pulumi (TypeScript) |
|---|---|---|
| **Language familiarity** (for JS/TS devs) | New language to learn | Already know it |
| **Loops and conditionals** | `count`, `for_each`, `dynamic` blocks (awkward) | Standard `for`, `if`, `map`, `filter` |
| **Type system** | Limited (variable types, no generics) | Full TypeScript type system |
| **Testing** | `terraform validate` (syntax only), terratest (Go) | Jest, Vitest, standard TS testing tools |
| **IDE autocomplete** | HCL plugin (decent but not TypeScript-level) | Full IntelliSense, go-to-definition, refactor |
| **Package ecosystem** | Terraform Registry (modules) | npm (infrastructure + general-purpose) |
| **State backend** | GCS, S3, Terraform Cloud, local | Pulumi Cloud (free tier), GCS, S3, local |
| **Community size** | Much larger (10+ years, dominant market share) | Smaller but growing fast |
| **Job market** | Industry standard (most job postings) | Increasingly listed, but Terraform dominates |
| **License** | BSL (Terraform) / MPL (OpenTofu) | Apache 2.0 (open source) |
| **Refactoring** | `terraform state mv` (manual, error-prone) | `pulumi state rename` (still manual but IDE helps) |
| **Import existing resources** | `terraform import` | `pulumi import` |
| **Secret management** | External (Vault, GCP Secret Manager) | Built-in encryption in state |
| **Documentation** | Excellent (years of community content) | Good (official docs are clear, fewer community posts) |

### Code Comparison: Same Infrastructure, Both Tools

Here is the same AI Doctor infrastructure defined in both Terraform and Pulumi, side by side.

**GKE Autopilot Cluster:**

```hcl
# Terraform
resource "google_container_cluster" "doctor" {
  name             = "doctor-cluster"
  location         = var.region
  enable_autopilot = true
  release_channel {
    channel = "REGULAR"
  }
}
```

```typescript
// Pulumi
const cluster = new gcp.container.Cluster("doctor-cluster", {
  location: region,
  enableAutopilot: true,
  releaseChannel: { channel: "REGULAR" },
});
```

**Artifact Registry:**

```hcl
# Terraform
resource "google_artifact_registry_repository" "doctor" {
  location      = var.region
  repository_id = "doctor-app"
  format        = "DOCKER"
}
```

```typescript
// Pulumi
const registry = new gcp.artifactregistry.Repository("doctor-app", {
  location: region,
  format: "DOCKER",
});
```

**IAM Service Account + Role Binding:**

```hcl
# Terraform
resource "google_service_account" "deployer" {
  account_id   = "github-deployer"
  display_name = "GitHub Actions Deployer"
}

resource "google_project_iam_member" "deployer_gke" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}
```

```typescript
// Pulumi
const deployer = new gcp.serviceaccount.Account("github-deployer", {
  accountId: "github-deployer",
  displayName: "GitHub Actions Deployer",
});

const deployerGke = new gcp.projects.IAMMember("deployer-gke", {
  project: projectId,
  role: "roles/container.developer",
  member: pulumi.interpolate`serviceAccount:${deployer.email}`,
});
```

**Workload Identity Binding (more complex -- shows language advantages):**

```hcl
# Terraform -- creating bindings for multiple K8s service accounts
variable "k8s_service_accounts" {
  type = list(object({
    name      = string
    namespace = string
  }))
  default = [
    { name = "doctor-backend", namespace = "doctor-app" },
    { name = "doctor-worker",  namespace = "doctor-app" },
  ]
}

resource "google_service_account_iam_member" "workload_identity" {
  for_each           = { for sa in var.k8s_service_accounts : sa.name => sa }
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${each.value.namespace}/${each.value.name}]"
}
```

```typescript
// Pulumi -- same thing, but with standard TypeScript
const k8sServiceAccounts = [
  { name: "doctor-backend", namespace: "doctor-app" },
  { name: "doctor-worker",  namespace: "doctor-app" },
];

for (const sa of k8sServiceAccounts) {
  new gcp.serviceaccount.IAMMember(`wi-${sa.name}`, {
    serviceAccountId: deployer.name,
    role: "roles/iam.workloadIdentityUser",
    member: pulumi.interpolate`serviceAccount:${projectId}.svc.id.goog[${sa.namespace}/${sa.name}]`,
  });
}
```

The Terraform version uses `for_each` with a map transformation -- functional but syntactically heavy. The Pulumi version uses a standard `for...of` loop that any TypeScript developer can read immediately.

---

## 11. Recommended Approach for AI Doctor Assistant

The recommendation follows a phased approach that balances pragmatism with learning:

### Phase 1 (Now): gcloud CLI Script

You are one developer working on a single project. You need a GKE cluster, an Artifact Registry repository, and a service account. That is 5 gcloud commands. Write them in a shell script, run it once, and move on to building features.

```bash
#!/bin/bash
# infra/gcp/bootstrap.sh
# Run once to set up GCP resources. Not idempotent.

set -euo pipefail

gcloud container clusters create-auto doctor-cluster --region=us-central1
gcloud artifacts repositories create doctor-app --repository-format=docker --location=us-central1
gcloud iam service-accounts create github-deployer --display-name="GitHub Actions Deployer"
```

This is not "good" IaC. It has no state, no plan, no drift detection. But it takes 5 minutes to write, works immediately, and you can replace it later. The overhead of setting up Terraform or Pulumi for 3 resources is not justified yet.

### Phase 2 (When Ready to Learn IaC): Pulumi with TypeScript

When you have more infrastructure to manage (multiple environments, Cloud SQL, VPC peering, DNS records, monitoring), switch to Pulumi. The reasoning:

- **You already know TypeScript.** The AI Doctor frontend is React + TypeScript. You will not need to learn a new language (HCL) to manage infrastructure.
- **IDE support is excellent.** TypeScript autocomplete on infrastructure resources is genuinely useful. When you type `new gcp.container.Cluster("...", {` and your IDE shows all available properties with their types, you learn the API faster than reading documentation.
- **Testing is familiar.** You can write unit tests for your infrastructure code with the same tools you use for frontend tests.
- **It is more fun.** This matters for a personal project. Writing TypeScript is more enjoyable than writing HCL, and you are more likely to maintain something you enjoy working with.

Project structure:

```
infra/
  pulumi/
    Pulumi.yaml          # Project config
    Pulumi.dev.yaml      # Dev stack config
    Pulumi.prod.yaml     # Prod stack config
    index.ts             # Main infrastructure code
    cluster.ts           # GKE cluster definition
    registry.ts          # Artifact Registry definition
    iam.ts               # Service accounts and IAM bindings
    package.json         # Dependencies (@pulumi/gcp, @pulumi/pulumi)
    tsconfig.json        # TypeScript config
```

### Phase 3 (Job Prep): Learn Terraform Too

Terraform is the industry standard. When a job posting says "experience with IaC," they almost always mean Terraform. When someone asks "how do you manage infrastructure?", saying "Pulumi" is a valid answer but saying "Terraform" gets more nods of recognition.

The good news: if you understand Pulumi, learning Terraform is straightforward. The concepts are identical (state, providers, plan/apply, resources, outputs). The difference is syntax (HCL vs TypeScript) and tooling. You can learn enough Terraform for professional work in a weekend.

The ideal outcome: use Pulumi for your own projects (better developer experience), know Terraform for professional contexts (industry standard). They are not mutually exclusive.

---

## 12. How IaC and K8s Tools Fit Together

This is the full picture of how every tool in the deployment pipeline relates to every other tool. Understanding these layers prevents confusion about which tool does what.

```
+-------------------------------------------------------------------+
|                        IaC Layer                                  |
|               (Pulumi / Terraform / gcloud CLI)                   |
|                                                                   |
|   What it creates:                                                |
|     - GKE Autopilot cluster                                       |
|     - Artifact Registry repository                                |
|     - IAM service accounts + role bindings                        |
|     - Workload Identity federation                                |
|     - VPC network (if custom networking needed)                   |
|     - Cloud SQL instance (future, replaces in-cluster Postgres)   |
|     - DNS records (future, for custom domain)                     |
|                                                                   |
|   Runs: once to set up, occasionally to update                    |
|   State: tracked in Pulumi Cloud / GCS bucket / Terraform Cloud   |
+------------------------------+------------------------------------+
                               |
                               | cluster exists, registry exists
                               | kubectl is authenticated
                               v
+-------------------------------------------------------------------+
|                     K8s Manifest Layer                             |
|                    (Kustomize / Helm)                              |
|                                                                   |
|   What it deploys:                                                |
|     - Deployments (doctor-backend, doctor-frontend)               |
|     - Services (ClusterIP for backend/postgres, Ingress)          |
|     - ConfigMaps (app configuration)                              |
|     - Secrets (API keys, database credentials)                    |
|     - Ingress rules (route /api/* to backend, /* to frontend)     |
|     - StatefulSets (PostgreSQL, if in-cluster)                    |
|     - HPA (autoscaling rules)                                     |
|                                                                   |
|   Runs: on every deployment (code change or config change)        |
|   Overlays: dev / staging / prod (via Kustomize)                  |
+------------------------------+------------------------------------+
                               |
                               | manifests applied to cluster
                               | pods are running
                               v
+-------------------------------------------------------------------+
|                       CI/CD Layer                                  |
|                (GitHub Actions / ArgoCD)                           |
|                                                                   |
|   What it automates:                                              |
|     - Build Docker images (multi-stage: backend + frontend)       |
|     - Push images to Artifact Registry                            |
|     - Run tests (pytest, vitest)                                  |
|     - Apply Kustomize overlays to GKE                             |
|     - (Future) ArgoCD watches git repo, auto-syncs manifests      |
|                                                                   |
|   Trigger: git push to main / PR merge / manual dispatch          |
+------------------------------+------------------------------------+
                               |
                               | images built, manifests applied
                               | app is live on GKE
                               v
+-------------------------------------------------------------------+
|                     Local Dev Layer                                |
|              (docker-compose / minikube + Skaffold)                |
|                                                                   |
|   docker-compose (daily development):                             |
|     - Backend: uvicorn with hot reload on port 8000               |
|     - Frontend: vite dev server on port 5173                      |
|     - PostgreSQL: container on port 5432                          |
|     - Fast iteration, no K8s overhead                             |
|                                                                   |
|   minikube + Skaffold (manifest validation):                      |
|     - Test Kustomize overlays before pushing to GKE               |
|     - Validate health probes, resource limits, service discovery  |
|     - Skaffold watches code and redeploys automatically           |
|     - Catch manifest errors locally, save cloud debugging time    |
|                                                                   |
|   kind (CI testing):                                              |
|     - GitHub Actions: spin up disposable K8s cluster              |
|     - Run integration tests against real K8s environment          |
|     - Fast startup, lightweight, purpose-built for CI             |
+-------------------------------------------------------------------+
```

### Layer Boundaries: What Each Tool Does NOT Do

Understanding the boundaries is as important as understanding the capabilities:

- **IaC (Pulumi/Terraform) does NOT deploy your application.** It creates the cluster and registry. It does not know about your Deployments, Services, or Pods. Some IaC tools CAN manage K8s resources, but mixing IaC and K8s manifest management in the same tool creates confusing ownership boundaries. Keep them separate.

- **Kustomize does NOT create cloud resources.** It applies manifests to a cluster that already exists. If the cluster does not exist, `kubectl apply` fails. Kustomize does not know about GKE, IAM, or Artifact Registry.

- **GitHub Actions does NOT manage infrastructure state.** It runs commands (`terraform apply`, `kubectl apply`) but does not own the state. The state lives in Pulumi Cloud, a GCS bucket, or the Kubernetes API server.

- **docker-compose does NOT test Kubernetes behavior.** It starts containers, but it does not use Kubernetes manifests, does not enforce resource limits the way K8s does, does not run health probes the way K8s does, and does not use K8s service discovery DNS.

- **minikube does NOT replace docker-compose for daily development.** The build-load-deploy cycle in minikube is slower than docker-compose's native volume mounts and hot reload. Use the right tool for the right job.

### The Decision Flow

When you ask "which tool should I use right now?", follow this flow:

```
What are you doing?
|
+-- Writing application code (Python, TypeScript)
|   +-- Use docker-compose
|
+-- Changing K8s manifests (Deployments, Services, Kustomize)
|   +-- Use minikube + kubectl apply -k
|
+-- Changing both code AND manifests frequently
|   +-- Use Skaffold + minikube
|
+-- Creating/modifying cloud resources (GKE cluster, IAM, registry)
|   +-- Use Pulumi / Terraform / gcloud CLI
|
+-- Setting up CI/CD pipeline
|   +-- Use GitHub Actions + kind (for K8s integration tests)
|
+-- Validating infrastructure knowledge
    +-- Learn Terraform (industry standard) + understand all layers above
```

---

## Summary

This document covered two complementary topics: running Kubernetes locally to validate manifests before cloud deployment, and defining cloud infrastructure as code rather than manual console operations.

**Local K8s development** gives you confidence that your Kustomize overlays, health probes, resource limits, and service discovery will work on GKE before you push. minikube is the recommended tool for local validation (closest to GKE, best addon support), kind is recommended for CI pipelines (fast, disposable), and Skaffold automates the build-deploy loop when you are iterating on both code and manifests.

**Infrastructure as Code** ensures your cloud resources are version-controlled, reproducible, and reviewable. For the AI Doctor Assistant, the pragmatic path is: start with a gcloud CLI script for initial setup, adopt Pulumi (TypeScript) when complexity grows, and learn Terraform for career value.

The tools form distinct layers: IaC creates the cluster, Kustomize deploys the application, CI/CD automates both, and local dev tools let you validate everything before it reaches the cloud. Each layer has clear boundaries. Keeping those boundaries clean prevents confusion about which tool is responsible for what.

> **AI Doctor Example:** The AI Doctor Assistant's full deployment pipeline looks like this: Pulumi creates the GKE cluster and Artifact Registry. GitHub Actions builds Docker images and pushes them to Artifact Registry on merge to main. Kustomize overlays define how the backend, frontend, and PostgreSQL are deployed, with separate configurations for dev, staging, and production. Before any of this reaches GKE, the developer validates manifests locally with minikube, catching configuration errors in 2 minutes instead of 15. docker-compose remains the daily driver for writing and testing application code.
