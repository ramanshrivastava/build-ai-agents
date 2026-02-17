# Security, Service Discovery, and Why Kubernetes

> **Document 11 of 12** in the [Infrastructure & Kubernetes Learning Guide](./00-OVERVIEW.md)
>
> **Purpose:** Answer the fundamental question "why Kubernetes instead of a VM?" with honest tradeoffs. Then cover the two topics most critical to running production workloads: security (five defense layers from cloud to application) and service discovery (how pods find each other). Finish with a deployment platform comparison so you can match the right tool to each problem.
>
> **Prerequisites:** Documents 01-06 (core K8s concepts, GKE, tooling, app mapping, CI/CD), Document 10 (nginx, Ingress controllers). You should understand Pods, Services, Deployments, Ingress, NetworkPolicies, and the AI Doctor Assistant architecture (FastAPI backend + React frontend + PostgreSQL).

---

## Table of Contents

### Part 1: Why Kubernetes at All?
1. [The Traditional VM Deployment](#1-the-traditional-vm-deployment)
2. [VM vs VPS vs Containers vs Kubernetes](#2-vm-vs-vps-vs-containers-vs-kubernetes)
3. [When to Use What](#3-when-to-use-what)
4. [The Hidden Costs of NOT Using K8s](#4-the-hidden-costs-of-not-using-k8s)

### Part 2: Kubernetes Security (5 Layers)
5. [Security Layer Model](#5-security-layer-model)
6. [Layer 1: Cloud/Infrastructure Security](#6-layer-1-cloudinfrastructure-security)
7. [Layer 2: Kubernetes RBAC](#7-layer-2-kubernetes-rbac)
8. [Layer 3: Network Security](#8-layer-3-network-security)
9. [Layer 4: Pod Security](#9-layer-4-pod-security)
10. [Layer 5: Application Security](#10-layer-5-application-security)
11. [Security Checklist for AI Doctor](#11-security-checklist-for-ai-doctor)

### Part 3: Service Discovery and Networking
12. [The Problem Service Discovery Solves](#12-the-problem-service-discovery-solves)
13. [How K8s DNS Works](#13-how-k8s-dns-works)
14. [Service Types and When to Use Each](#14-service-types-and-when-to-use-each)
15. [How Microservices Find Each Other](#15-how-microservices-find-each-other)
16. [Ingress vs Service vs Pod Networking](#16-ingress-vs-service-vs-pod-networking)
17. [When Services Are Not Enough: Service Mesh](#17-when-services-are-not-enough-service-mesh)

### Part 4: Deployment Comparison
18. [Where to Deploy Different Types of Apps](#18-where-to-deploy-different-types-of-apps)
19. [Summary](#19-summary)

---

## Part 1: Why Kubernetes at All?

Before diving into security and networking, we need to address the elephant in the room. Kubernetes is complex. It has a steep learning curve. For many applications, it is overkill. This section explains when K8s is worth the complexity and when simpler alternatives are the right call.

---

## 1. The Traditional VM Deployment

To understand why Kubernetes exists, you need to understand what came before it. Here is what deploying the AI Doctor Assistant looks like on a single virtual machine.

### The Manual Process

You rent a VPS from DigitalOcean, Hetzner, or AWS EC2. Then you SSH in and start setting things up:

```bash
# 1. SSH into the server
ssh root@203.0.113.42

# 2. Install system dependencies
apt update && apt upgrade -y
apt install -y python3.12 python3.12-venv nodejs npm nginx certbot postgresql-16

# 3. Clone the repo
git clone https://github.com/you/ai-doctor-assistant.git /opt/doctor-app

# 4. Set up the backend
cd /opt/doctor-app/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # or: uv sync
cp .env.example .env
# Edit .env with real credentials...

# 5. Set up PostgreSQL
sudo -u postgres createuser doctor
sudo -u postgres createdb doctor_db -O doctor

# 6. Set up the frontend
cd /opt/doctor-app/frontend
npm ci
npm run build
cp -r dist/* /var/www/html/doctor-app/

# 7. Configure nginx (TLS, reverse proxy, static files)
cp nginx.conf /etc/nginx/sites-available/doctor-app
ln -s /etc/nginx/sites-available/doctor-app /etc/nginx/sites-enabled/
certbot --nginx -d doctor-app.example.com

# 8. Create a systemd service for the backend
cat > /etc/systemd/system/doctor-backend.service << EOF
[Unit]
Description=AI Doctor Backend
After=postgresql.service

[Service]
User=www-data
WorkingDirectory=/opt/doctor-app/backend
ExecStart=/opt/doctor-app/backend/.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl enable doctor-backend
systemctl start doctor-backend

# 9. Verify everything works
curl -s http://localhost:8000/health
curl -s https://doctor-app.example.com/
```

That is 40+ commands across multiple tools. And you typed every one of them by hand.

### What This Looks Like

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SINGLE VPS ($5-20/month)                          │
│                    Ubuntu 22.04, 2 vCPU, 4GB RAM                    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                nginx (port 80/443)                           │   │
│  │  - TLS termination (Let's Encrypt)                          │   │
│  │  - Serves React static files from /var/www/html             │   │
│  │  - Reverse proxies /api/* to localhost:8000                 │   │
│  └──────────┬──────────────────────┬───────────────────────────┘   │
│             │                      │                                │
│      static files           proxy /api/*                           │
│             │                      │                                │
│             ▼                      ▼                                │
│  ┌──────────────────┐   ┌──────────────────────────┐              │
│  │  /var/www/html    │   │  uvicorn (port 8000)     │              │
│  │  React build      │   │  FastAPI + Python 3.12   │              │
│  │  files            │   │  managed by systemd      │              │
│  └──────────────────┘   └────────────┬─────────────┘              │
│                                       │                             │
│                                       ▼                             │
│                           ┌──────────────────────┐                 │
│                           │  PostgreSQL 16        │                 │
│                           │  port 5432            │                 │
│                           │  data: /var/lib/pg    │                 │
│                           └──────────────────────┘                 │
│                                                                     │
│  Also running: certbot renewal cron, fail2ban, unattended-upgrades │
└─────────────────────────────────────────────────────────────────────┘
```

### The Problems

This works. Millions of applications run exactly like this. But it has real problems:

**Snowflake servers.** Every setup command was typed by hand. If the server dies, can you recreate it exactly? Did you remember every `apt install`, every config tweak, every environment variable? Probably not. The server becomes a unique snowflake that nobody can reproduce.

**Manual scaling.** Traffic spikes. You need a second server. You SSH into a new VPS and repeat every step. Then you configure a load balancer between the two. Scaling down means carefully decommissioning a server. None of this is automated.

**No self-healing.** The backend process crashes at 3 AM. systemd restarts it, but what if systemd itself has a problem? What if the server's disk fills up? You get a monitoring alert and manually intervene.

**Config drift.** Six months later, someone SSH'd in and installed a debugging tool. Someone else tweaked an nginx setting. The server no longer matches any documentation. You have no idea what state it is actually in.

**Deployment risk.** You `git pull` and `systemctl restart`. If the new code has a bug, your app is down until you notice and roll back manually. There is no rolling update, no health check, no automatic rollback.

**Environment inconsistency.** "It works on my machine." Your laptop runs macOS, the server runs Ubuntu 22.04. Python version mismatches, library version mismatches, missing system packages. The development environment and production environment are fundamentally different.

---

## 2. VM vs VPS vs Containers vs Kubernetes

These four terms get conflated constantly. Here is what each one actually means.

### Virtual Machine (VM)

A VM is a virtualized computer running on a **hypervisor** (software that creates and manages VMs). The hypervisor runs on physical hardware and allocates CPU, memory, disk, and network to each VM. Each VM runs a **complete operating system** -- its own kernel, its own system libraries, its own file system.

```
┌─────────────────────────────────────────────────────────────┐
│                    Physical Server                            │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │    VM 1           │  │    VM 2           │                │
│  │  ┌─────────────┐ │  │  ┌─────────────┐ │                │
│  │  │ Your App    │ │  │  │ Your App    │ │                │
│  │  ├─────────────┤ │  │  ├─────────────┤ │                │
│  │  │ Libraries   │ │  │  │ Libraries   │ │                │
│  │  ├─────────────┤ │  │  ├─────────────┤ │                │
│  │  │ Full OS     │ │  │  │ Full OS     │ │                │
│  │  │ (kernel)    │ │  │  │ (kernel)    │ │                │
│  │  └─────────────┘ │  │  └─────────────┘ │                │
│  └──────────────────┘  └──────────────────┘                │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Hypervisor (VMware, KVM, Xen)           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Physical Hardware                        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### VPS (Virtual Private Server)

A VPS is simply a VM that someone else hosts. When you rent a $5/month DigitalOcean Droplet, you are renting a VM on DigitalOcean's physical hardware. The technical architecture is identical to running your own VM -- the difference is operational: someone else manages the physical servers, networking, and hypervisor.

**VM = the technology. VPS = the business model.** DigitalOcean, Hetzner, Linode, Vultr, and AWS EC2 all sell VPS instances. When this document says "VM deployment," it applies equally to VPS providers.

### Container

A container is an **isolated process** that shares the host operating system's kernel. Unlike a VM, a container does not run its own OS kernel. It uses Linux kernel features -- **namespaces** (isolated view of processes, network, filesystem) and **cgroups** (resource limits) -- to create isolation between processes.

```
┌─────────────────────────────────────────────────────────────┐
│                    Physical or Virtual Server                 │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Container 1  │  │ Container 2  │  │ Container 3  │     │
│  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │     │
│  │ │ Your App │ │  │ │ Your App │ │  │ │ Your App │ │     │
│  │ ├──────────┤ │  │ ├──────────┤ │  │ ├──────────┤ │     │
│  │ │ Libs     │ │  │ │ Libs     │ │  │ │ Libs     │ │     │
│  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Container Runtime (containerd, Docker)      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Single OS Kernel (shared)                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Kubernetes

Kubernetes orchestrates containers across a cluster of multiple nodes (machines). It adds scheduling (which node runs which container), scaling, self-healing, service discovery, load balancing, and configuration management on top of containers.

### Comparison Table

| Aspect | VM / VPS | Container | Kubernetes |
|---|---|---|---|
| **What it is** | Full virtualized computer | Isolated process on shared kernel | Container orchestration platform |
| **OS kernel** | Dedicated per VM | Shared with host | Shared with host (per node) |
| **Image size** | 1-40 GB | 10-500 MB | N/A (manages container images) |
| **Startup time** | 30 seconds - 5 minutes | 1-10 seconds | 5-30 seconds (scheduling + pull + start) |
| **Resource overhead** | High (full OS per VM) | Low (shared kernel) | Medium (K8s components + containers) |
| **Isolation** | Strong (hardware-level via hypervisor) | Moderate (kernel namespaces/cgroups) | Moderate (container isolation + NetworkPolicy) |
| **Scaling** | Manual: provision new VM, configure, deploy | Manual: `docker run` on another host | Automatic: `replicas: 5` or HPA |
| **Self-healing** | None (manual intervention) | Restart policies per container | Full: restart, reschedule, replace |
| **Networking** | Static IPs, manual firewall rules | docker-compose networks, port mapping | Built-in DNS, Services, Ingress |
| **Config management** | SSH + edit files manually | docker-compose.yml, env files | ConfigMaps, Secrets, declarative YAML |
| **Reproducibility** | Low (snowflake risk) | High (Dockerfile is reproducible) | High (YAML manifests in git) |
| **Rolling updates** | Manual: deploy new, switch traffic, stop old | Manual with docker-compose | Built-in: `strategy: RollingUpdate` |
| **Cost (small app)** | $5-20/month | Same as VM (runs on a VM) | $70-200+/month (managed K8s) |
| **Complexity** | Low | Low-moderate | High |
| **Learning curve** | Low (SSH + Linux basics) | Low-moderate (Docker) | High (many abstractions to learn) |
| **Best for** | Simple apps, single server | Multi-service on one machine | Multi-service, scaling, team operations |

---

## 3. When to Use What

### Decision Flowchart

```
                        ┌─────────────────────┐
                        │  How many services   │
                        │  does your app have? │
                        └──────────┬──────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
               1 service     2-5 services    6+ services
                    │              │              │
                    ▼              ▼              ▼
           ┌───────────┐  ┌──────────────┐  ┌──────────────┐
           │ Need auto- │  │ Fit on one   │  │ Need auto-   │
           │ scaling?   │  │ machine?     │  │ scaling or   │
           └─────┬─────┘  └──────┬───────┘  │ rolling      │
                 │               │           │ updates?     │
           ┌─────┼─────┐   ┌────┼────┐     └──────┬───────┘
           │           │   │         │            │
           No         Yes  Yes       No      ┌────┴────┐
           │           │   │         │        │         │
           ▼           ▼   ▼         ▼        No       Yes
        ┌──────┐  ┌────────┐ ┌──────────┐    │         │
        │ VPS  │  │Cloud   │ │docker-   │    ▼         ▼
        │      │  │Run /   │ │compose   │ ┌──────┐ ┌──────────┐
        │      │  │Lambda/ │ │on a VPS  │ │d-c on│ │Kubernetes│
        │      │  │Workers │ │          │ │multi │ │          │
        └──────┘  └────────┘ └──────────┘ │VPS   │ └──────────┘
                                           └──────┘
```

### The Options, Explained

**VPS / VM (single server):** Your app is simple. A FastAPI server, maybe a database. Traffic is predictable -- tens to thousands of requests per day, not millions. You know Linux basics. Budget is tight. This is the right choice for most side projects, internal tools, and early-stage startups.

**docker-compose on a VPS:** You have multiple services (backend, frontend, database, Redis, worker) but they all fit on one machine. docker-compose gives you reproducible multi-service deployment on a single host. This is AI Doctor's local development setup today, and it would work fine in production at current scale.

**Kubernetes:** You need automated scaling, rolling updates with zero downtime, self-healing, or your team has multiple developers deploying multiple services. The complexity overhead is justified by operational benefits. Suitable when you have moved past the prototype stage and need production reliability.

**Serverless (Cloudflare Workers, AWS Lambda, Google Cloud Run):** Your application is stateless, handles bursty traffic (quiet most of the time, spikes for short periods), and fits the request-response model. Great for APIs, webhooks, scheduled tasks. Not suitable for long-running processes or stateful workloads.

### AI Doctor: Honest Assessment

```
AI DOCTOR EXAMPLE:
The AI Doctor Assistant has 3 services: FastAPI backend, React frontend,
PostgreSQL database. Traffic is low (internal medical tool, not public-facing).

HONEST ANSWER: A $10/month VPS with docker-compose would run this app
perfectly fine in production. Kubernetes is chosen here as a LEARNING
INVESTMENT, not because the app demands it.

When K8s WOULD be justified for AI Doctor:
  - Multiple hospitals using the system (need scaling)
  - Team of 5+ developers deploying independently
  - Compliance requirements demanding audit trails and RBAC
  - Adding ML model inference service (GPU scheduling)
  - Moving from monolith to microservices architecture

For now, we use K8s to learn production patterns. This is valuable
because the skills transfer to any future project that DOES need K8s.
```

---

## 4. The Hidden Costs of NOT Using K8s

Even though K8s is overkill for a small app, understanding what you lose without it clarifies why larger teams adopt it.

### What You Do Manually Without K8s

| Concern | Without K8s (VPS) | With K8s |
|---|---|---|
| **App crashes** | systemd restarts it (single machine only) | Pod rescheduled to healthy node, across cluster |
| **Deploy new version** | `git pull && systemctl restart` (brief downtime) | Rolling update: new pods start before old pods stop |
| **Scale up** | Provision new VPS, install everything, configure LB | `kubectl scale deploy backend --replicas=5` |
| **Scale down** | Decommission server carefully | `kubectl scale deploy backend --replicas=1` |
| **TLS certificates** | Certbot + cron renewal (breaks sometimes) | cert-manager + Let's Encrypt (fully automated) |
| **Load balancing** | Configure HAProxy or nginx upstream manually | K8s Service does it automatically |
| **Secrets** | `.env` files on disk (easy to leak) | K8s Secrets with RBAC, external secret managers |
| **Config consistency** | Dev laptop != staging server != production server | Same YAML manifests across all environments |
| **Rollback bad deploy** | `git checkout old-version && restart` (manual) | `kubectl rollout undo deployment/backend` (instant) |
| **Multiple environments** | Maintain separate servers with separate configs | Kustomize overlays: `base/` + `overlays/dev/` + `overlays/prod/` |

### The Honest Tradeoff

Kubernetes solves real operational problems. But it introduces its own costs:

- **Learning curve:** Weeks to months to become productive
- **Complexity:** Debugging K8s issues requires understanding multiple abstractions
- **Cost:** Managed K8s (GKE, EKS) costs more than a VPS for small workloads
- **YAML sprawl:** 20+ manifest files for a 3-service app
- **Cognitive load:** Developers need to understand pods, services, ingress, configmaps, secrets, deployments, namespaces...

**The rule of thumb:** If you are a solo developer with one app and predictable traffic, a VPS with docker-compose is simpler, cheaper, and faster to set up. If you are a team deploying multiple services with production reliability requirements, Kubernetes pays for itself.

---

## Part 2: Kubernetes Security (5 Layers)

Security in Kubernetes is not a single setting you enable. It is a series of layers, each catching what the previous one misses. This defense-in-depth approach means a breach in one layer does not compromise the entire system.

---

## 5. Security Layer Model

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  LAYER 1: CLOUD / INFRASTRUCTURE                                         │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ IAM roles, private clusters, VPC, firewalls, node security        │  │
│  │                                                                    │  │
│  │  LAYER 2: KUBERNETES RBAC                                          │  │
│  │  ┌────────────────────────────────────────────────────────────┐   │  │
│  │  │ ServiceAccounts, Roles, RoleBindings, least privilege      │   │  │
│  │  │                                                            │   │  │
│  │  │  LAYER 3: NETWORK SECURITY                                 │   │  │
│  │  │  ┌────────────────────────────────────────────────────┐   │   │  │
│  │  │  │ NetworkPolicies, pod-to-pod firewall, DNS policies │   │   │  │
│  │  │  │                                                    │   │   │  │
│  │  │  │  LAYER 4: POD SECURITY                             │   │   │  │
│  │  │  │  ┌────────────────────────────────────────────┐   │   │   │  │
│  │  │  │  │ SecurityContext, non-root, read-only FS,   │   │   │   │  │
│  │  │  │  │ dropped capabilities, resource limits      │   │   │   │  │
│  │  │  │  │                                            │   │   │   │  │
│  │  │  │  │  LAYER 5: APPLICATION SECURITY              │   │   │   │  │
│  │  │  │  │  ┌────────────────────────────────────┐   │   │   │   │  │
│  │  │  │  │  │ Secrets management, TLS, input      │   │   │   │   │  │
│  │  │  │  │  │ validation, CORS, logging,          │   │   │   │   │  │
│  │  │  │  │  │ no patient data in logs             │   │   │   │   │  │
│  │  │  │  │  └────────────────────────────────────┘   │   │   │   │  │
│  │  │  │  └────────────────────────────────────────────┘   │   │   │  │
│  │  │  └────────────────────────────────────────────────────┘   │   │  │
│  │  └────────────────────────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

Each layer operates independently. If an attacker bypasses Layer 1 (gains cloud access), Layer 2 (RBAC) limits what they can do. If they bypass RBAC, Layer 3 (NetworkPolicies) prevents lateral movement. If they get into a pod, Layer 4 (SecurityContext) limits what the process can do. If they exploit the application, Layer 5 (secrets management, input validation) limits the damage.

---

## 6. Layer 1: Cloud/Infrastructure Security

This is the outermost layer. It controls who can access your cluster and how the underlying infrastructure is secured.

### IAM (Identity and Access Management)

GCP IAM controls which humans and service accounts can interact with your GKE cluster. Key roles:

| IAM Role | What It Grants | Who Gets It |
|---|---|---|
| `roles/container.admin` | Full control over clusters and K8s resources | Cluster administrators only |
| `roles/container.developer` | Deploy to existing clusters, manage workloads | Developers on the team |
| `roles/container.viewer` | Read-only access to cluster and workloads | Monitoring tools, auditors |
| `roles/container.clusterViewer` | View cluster metadata only (not workloads) | Billing, project managers |

**Principle of least privilege:** Never grant `container.admin` to developers who only need to deploy workloads. Grant the minimum role required for each person's job function.

### Private Clusters

By default, a GKE cluster's API server is accessible from the public internet. Anyone who knows the endpoint can attempt to authenticate. A **private cluster** restricts API server access to authorized networks only:

```bash
# Create a private cluster (API server not publicly accessible)
gcloud container clusters create doctor-cluster \
  --enable-private-nodes \
  --enable-private-endpoint \
  --master-ipv4-cidr 172.16.0.0/28 \
  --enable-master-authorized-networks \
  --master-authorized-networks 203.0.113.0/24  # Your office IP range
```

With a private cluster, `kubectl` commands only work from authorized networks (your office, a VPN, or Cloud Shell).

### Workload Identity

Workload Identity lets pods authenticate to GCP services (Cloud SQL, Secret Manager, Cloud Storage) **without storing key files** in Secrets or environment variables. It links a Kubernetes ServiceAccount to a GCP IAM ServiceAccount:

```
┌──────────────────────────────────┐     ┌─────────────────────────────┐
│  K8s ServiceAccount              │     │  GCP IAM ServiceAccount     │
│  name: backend-sa                │────►│  name: doctor-backend@      │
│  namespace: doctor-app           │     │        project.iam.gsa.com  │
│                                  │     │                             │
│  (identity inside the cluster)   │     │  Has IAM roles:             │
│                                  │     │  - secretmanager.accessor   │
│                                  │     │  - cloudsql.client          │
└──────────────────────────────────┘     └─────────────────────────────┘
```

The backend pod runs with the K8s ServiceAccount. When it calls a GCP API, GKE automatically provides a token tied to the GCP IAM ServiceAccount. No JSON key files, no environment variables with credentials.

### VPC and Firewall Rules

VPC (Virtual Private Cloud) isolates your cluster's network. Firewall rules control traffic at the network level (before it reaches Kubernetes):

- **Allow** HTTPS (443) from the internet to the load balancer
- **Allow** internal traffic between nodes in the cluster
- **Deny** SSH to nodes from the internet (use Cloud Shell or IAP tunnel instead)
- **Deny** all other inbound traffic

### Node Security

GKE provides several node-level security features:

- **Auto-upgrades:** Nodes automatically receive security patches and K8s version updates
- **Shielded nodes:** Secure boot, verified boot integrity, vTPM for tamper detection
- **Container-Optimized OS (COS):** Minimal Linux distribution designed specifically for running containers -- reduced attack surface compared to Ubuntu or Debian
- **Node auto-repair:** GKE detects unhealthy nodes and replaces them automatically

```
AI DOCTOR EXAMPLE:
Minimal IAM setup for AI Doctor:

1. You (admin): roles/container.admin (manage cluster)
2. CI/CD pipeline: roles/container.developer (deploy workloads)
3. Backend pods: Workload Identity → GCP SA with secretmanager.accessor
4. Private cluster: API server accessible only from your IP and CI/CD runner
5. Nodes: COS images, auto-upgrade enabled, shielded nodes
```

---

## 7. Layer 2: Kubernetes RBAC

RBAC (Role-Based Access Control) controls what authenticated entities can do *inside* the cluster. Layer 1 (IAM) controls who can *access* the cluster. Layer 2 controls what they can *do* once inside.

### Authentication vs Authorization

**Authentication** answers: "Who are you?" Kubernetes authenticates via certificates, tokens, or identity provider integration. In GKE, authentication typically uses Google Cloud IAM tokens.

**Authorization** answers: "What can you do?" After authentication, RBAC checks whether the authenticated identity has permission to perform the requested action.

### The RBAC Model

RBAC has four key objects:

```
┌──────────────────┐          ┌──────────────────┐
│  Role             │          │  ClusterRole      │
│  (namespace-      │          │  (cluster-wide    │
│   scoped)         │          │   permissions)    │
│                   │          │                   │
│  Defines:         │          │  Defines:         │
│  - resources      │          │  - resources      │
│  - verbs          │          │  - verbs          │
└────────┬─────────┘          └────────┬─────────┘
         │                             │
         │  bound via                  │  bound via
         ▼                             ▼
┌──────────────────┐          ┌──────────────────┐
│  RoleBinding      │          │ ClusterRole-     │
│  (namespace-      │          │ Binding          │
│   scoped)         │          │ (cluster-wide)   │
│                   │          │                   │
│  Assigns Role to: │          │  Assigns Role to:│
│  - User           │          │  - User          │
│  - Group          │          │  - Group         │
│  - ServiceAccount │          │  - ServiceAccount│
└──────────────────┘          └──────────────────┘
```

### ServiceAccounts

A **ServiceAccount** provides identity for pods. When a pod runs, it authenticates to the Kubernetes API using its ServiceAccount's token. Every namespace has a `default` ServiceAccount, but the `default` account often has more permissions than necessary.

Best practice: create a dedicated ServiceAccount for each application with only the permissions it needs.

```yaml
# ServiceAccount for the backend pods
apiVersion: v1
kind: ServiceAccount
metadata:
  name: backend-sa
  namespace: doctor-app
```

### Roles and RoleBindings

A **Role** defines a set of permissions (verbs on resources) within a namespace. A **RoleBinding** grants those permissions to a subject (user, group, or ServiceAccount).

```yaml
# Role: allow reading Secrets in doctor-app namespace
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: secret-reader
  namespace: doctor-app
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list"]

---
# RoleBinding: grant secret-reader to backend ServiceAccount
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: backend-reads-secrets
  namespace: doctor-app
subjects:
  - kind: ServiceAccount
    name: backend-sa
    namespace: doctor-app
roleRef:
  kind: Role
  name: secret-reader
  apiGroup: rbac.authorization.k8s.io
```

### Common RBAC Verbs

| Verb | What It Permits |
|---|---|
| `get` | Read a single named resource |
| `list` | Read all resources of a type |
| `watch` | Stream changes to resources |
| `create` | Create new resources |
| `update` | Modify existing resources |
| `patch` | Partially modify existing resources |
| `delete` | Remove resources |

### Least Privilege Examples

| Component | Permissions Needed | Why |
|---|---|---|
| Backend pods | Read Secrets in `doctor-app` | Needs ANTHROPIC_API_KEY and DATABASE_URL |
| Frontend pods | None (no K8s API calls) | nginx serves static files, never calls K8s API |
| CI/CD pipeline | Create/update Deployments, Services | Needs to deploy new versions |
| Monitoring | Read pods, events, metrics | Needs visibility but not modification rights |

```
AI DOCTOR EXAMPLE:
The backend ServiceAccount (backend-sa) can:
  - Read Secrets in the doctor-app namespace (API keys, DB password)
  - Nothing else. Cannot create pods, delete services, or read
    resources in other namespaces.

The frontend pods use the default ServiceAccount with NO additional
role bindings. nginx never calls the Kubernetes API.

This means: even if an attacker compromises the frontend pod, they
cannot access any K8s Secrets or modify any cluster resources.
```

---

## 8. Layer 3: Network Security

### The Dangerous Default

By default, Kubernetes has a **flat network**: every pod can communicate with every other pod in the cluster, across all namespaces. There are no firewalls between pods.

This means: if an attacker compromises the frontend pod, they can directly connect to PostgreSQL on port 5432. They can connect to the backend on port 8000. They can connect to any pod in any namespace. The flat network is the most dangerous default in Kubernetes.

```
DEFAULT BEHAVIOR (NO NetworkPolicies):

┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend    │────►│  Backend    │────►│  PostgreSQL  │
│  Pod         │◄────│  Pod        │◄────│  Pod         │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                    │
       │   ALL pods can    │   ALL pods can     │
       │   talk to ALL     │   talk to ALL      │
       │   other pods      │   other pods       │
       ▼                   ▼                    ▼
  ┌──────────────────────────────────────────────────┐
  │  Any pod in ANY namespace can connect to any     │
  │  other pod on any port. No restrictions.         │
  └──────────────────────────────────────────────────┘
```

### NetworkPolicies: Pod-Level Firewall

**NetworkPolicies** are the solution. They act as firewall rules at the pod level, controlling which pods can communicate with which other pods.

A NetworkPolicy has two parts:
- **Ingress rules:** Who can connect TO this pod
- **Egress rules:** Where can this pod connect TO

**Important:** NetworkPolicies require a CNI plugin that supports them (Calico, Cilium, Weave Net). GKE supports NetworkPolicies natively when the feature is enabled.

### AI Doctor Network Security Design

Here is what the network security should look like for AI Doctor:

```
DESIRED BEHAVIOR (WITH NetworkPolicies):

                    Internet
                       │
                       ▼
              ┌──────────────────┐
              │ Ingress Controller│
              └───────┬──────────┘
                      │
         ┌────────────┼────────────┐
         │ ALLOWED    │ ALLOWED    │
         ▼            ▼            │
┌─────────────┐  ┌─────────────┐  │
│  Frontend   │  │  Backend    │  │
│  Pod        │  │  Pod        │  │
│             │  │         ────┼──┼──► Claude API (external)
│  BLOCKED:   │  │             │  │
│  Cannot     │  │  ALLOWED:   │
│  reach      │  │  Can reach  │
│  backend    │  │  postgres   │
│  directly   │  │             │
│             │  │  BLOCKED:   │
│  Cannot     │  │  Cannot     │
│  reach      │  │  reach      │
│  postgres   │  │  frontend   │
└─────────────┘  └──────┬──────┘
                        │ ALLOWED
                        ▼
                 ┌─────────────┐
                 │ PostgreSQL  │
                 │ Pod         │
                 │             │
                 │ BLOCKED:    │
                 │ Cannot      │
                 │ reach       │
                 │ anything    │
                 │ (no egress) │
                 └─────────────┘
```

### NetworkPolicy YAML Examples

**Default deny all ingress in the namespace** (start with deny, then allow selectively):

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: doctor-app
spec:
  podSelector: {}    # Applies to ALL pods in namespace
  policyTypes:
    - Ingress        # Deny all incoming traffic by default
```

**Allow Ingress controller to reach frontend and backend:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-to-frontend
  namespace: doctor-app
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
      ports:
        - protocol: TCP
          port: 80
```

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-to-backend
  namespace: doctor-app
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8000
```

**Allow only backend to reach PostgreSQL:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-backend-to-postgres
  namespace: doctor-app
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: backend
      ports:
        - protocol: TCP
          port: 5432
```

**Allow backend to reach external APIs (Claude) and DNS:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-egress
  namespace: doctor-app
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
    - Egress
  egress:
    # Allow DNS resolution
    - to: []
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # Allow HTTPS to external APIs (Claude API)
    - to: []
      ports:
        - protocol: TCP
          port: 443
    # Allow connection to PostgreSQL within namespace
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - protocol: TCP
          port: 5432
```

**Lock down PostgreSQL egress (it should not connect to anything):**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-deny-egress
  namespace: doctor-app
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
    - Egress
  egress:
    # Allow DNS only (PostgreSQL needs DNS for startup health checks)
    - to: []
      ports:
        - protocol: UDP
          port: 53
```

```
AI DOCTOR EXAMPLE:
With these NetworkPolicies in place:
  - Frontend pods: receive traffic from Ingress only, cannot reach
    backend or postgres directly
  - Backend pods: receive traffic from Ingress, connect to postgres
    on 5432 and external HTTPS (Claude API) on 443
  - PostgreSQL pods: receive traffic from backend on 5432 only,
    cannot initiate connections to anything except DNS

If an attacker compromises the frontend pod, they CANNOT:
  - Connect to PostgreSQL (blocked by NetworkPolicy)
  - Connect to the backend API directly (blocked by NetworkPolicy)
  - Connect to any pod in other namespaces (blocked by default deny)
```

---

## 9. Layer 4: Pod Security

Pod security controls what processes inside containers can do at the operating system level.

### SecurityContext

The `securityContext` field in a Pod spec restricts the container's Linux capabilities:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: doctor-app
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true          # Container MUST run as non-root user
        runAsUser: 1000             # Run as UID 1000
        runAsGroup: 1000            # Run as GID 1000
        fsGroup: 1000              # Files created belong to GID 1000
      containers:
        - name: fastapi
          image: us-central1-docker.pkg.dev/PROJECT/doctor-app/backend:latest
          securityContext:
            allowPrivilegeEscalation: false   # Cannot gain more privileges
            readOnlyRootFilesystem: true      # Cannot write to filesystem
            capabilities:
              drop:
                - ALL                          # Drop all Linux capabilities
          volumeMounts:
            - name: tmp
              mountPath: /tmp                  # Writable tmp dir (required by Python)
      volumes:
        - name: tmp
          emptyDir: {}                         # Ephemeral writable volume
```

### What Each Setting Does

| Setting | What It Prevents | Why It Matters |
|---|---|---|
| `runAsNonRoot: true` | Running as root user (UID 0) | Root inside container = root on node in many exploits |
| `readOnlyRootFilesystem: true` | Writing to the container filesystem | Prevents malware installation, config tampering |
| `allowPrivilegeEscalation: false` | Gaining additional privileges after start | Prevents `sudo`, setuid binaries, kernel exploits |
| `capabilities.drop: [ALL]` | All Linux capabilities (raw sockets, mount, etc.) | Minimizes kernel attack surface |

### Pod Security Standards

Kubernetes defines three levels of pod security:

| Standard | What It Allows | Use Case |
|---|---|---|
| **Privileged** | Everything. No restrictions. | System-level tools (monitoring agents, CNI plugins) |
| **Baseline** | Blocks known privilege escalation paths | General-purpose workloads |
| **Restricted** | Most restrictive. Non-root, read-only FS, dropped capabilities | Security-sensitive workloads (AI Doctor) |

You enforce these via the **Pod Security Admission** controller by labeling namespaces:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: doctor-app
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/audit: restricted
```

With `enforce: restricted`, Kubernetes rejects any pod that does not meet the restricted standard (non-root, no privilege escalation, dropped capabilities).

### Resource Limits

Resource limits prevent a single pod from consuming all node resources (intentional or accidental DoS):

```yaml
resources:
  requests:
    cpu: "250m"       # Guaranteed 25% of one core
    memory: "256Mi"   # Guaranteed 256MB
  limits:
    cpu: "1000m"      # Cannot exceed 1 full core
    memory: "512Mi"   # Killed if exceeds 512MB (OOMKilled)
```

Without limits, a memory leak in the backend could consume all node memory, crashing every other pod on that node.

### Image Security

- **Pull from trusted registries only:** Use Artifact Registry (GCP) or a private Docker registry. Do not pull from Docker Hub for production workloads.
- **Image scanning:** Artifact Registry automatically scans images for known vulnerabilities (CVEs).
- **Immutable tags:** Use image digests (`@sha256:...`) or specific version tags (`v2.1.0`), never `latest` in production.

```
AI DOCTOR EXAMPLE:
All AI Doctor pods run with restricted security:
  - runAsNonRoot: true (backend runs as UID 1000, nginx runs as nginx user)
  - readOnlyRootFilesystem: true (writable /tmp via emptyDir)
  - capabilities.drop: [ALL]
  - allowPrivilegeEscalation: false
  - Resource limits: backend 1 CPU / 512Mi, frontend 200m CPU / 128Mi
  - Images pulled from Artifact Registry (us-central1-docker.pkg.dev)
  - Namespace enforces restricted Pod Security Standard
```

---

## 10. Layer 5: Application Security

The innermost layer. Even with perfect infrastructure security, application-level vulnerabilities can leak data.

### Secrets Management

**K8s Secrets are base64-encoded, NOT encrypted by default.** Anyone with `get secrets` permission can decode them with a single command:

```bash
kubectl get secret ai-credentials -o jsonpath='{.data.anthropic_key}' | base64 -d
```

For production, use one of these approaches:

| Approach | Complexity | Security Level |
|---|---|---|
| K8s Secrets (default) | Low | Base64 only, stored in etcd |
| K8s Secrets + etcd encryption | Medium | Encrypted at rest in etcd |
| External Secrets Operator + GCP Secret Manager | Medium-high | Secrets stored outside cluster, synced to K8s |
| Workload Identity + direct GCP API calls | High | Secrets never stored in K8s at all |

For AI Doctor, the pragmatic starting point is K8s Secrets with etcd encryption enabled. When moving to production with real patient data, use External Secrets Operator with GCP Secret Manager.

### TLS

TLS is handled at the Ingress layer, not inside the application. The Ingress controller terminates HTTPS and forwards plain HTTP to backend pods. This was covered in detail in Document 10.

For automated certificate management, use **cert-manager** with Let's Encrypt:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
      - http01:
          ingress:
            class: nginx
```

### API Authentication Between Services

Within the cluster, traffic between services is generally trusted (especially with NetworkPolicies in place). For additional security between internal services:

- **JWT tokens:** Backend validates tokens from the frontend
- **mTLS (mutual TLS):** Both client and server present certificates (typically via service mesh)

For AI Doctor at current scale, NetworkPolicies provide sufficient inter-service security. mTLS is overkill.

### Input Validation and CORS

FastAPI provides built-in request validation via Pydantic models. CORS (Cross-Origin Resource Sharing) should be configured to allow only the frontend domain:

```python
# backend/src/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://doctor-app.example.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
```

In Kubernetes, CORS can also be configured via Ingress annotations:

```yaml
annotations:
  nginx.ingress.kubernetes.io/enable-cors: "true"
  nginx.ingress.kubernetes.io/cors-allow-origin: "https://doctor-app.example.com"
```

### Logging and Auditing

**Critical rule for medical applications: never log patient data.**

```python
# WRONG: Logs patient information
logger.info(f"Generating briefing for patient {patient.name}, DOB {patient.dob}")

# RIGHT: Logs only identifiers
logger.info(f"Generating briefing for patient_id={patient.id}")
```

Kubernetes audit logging tracks API calls to the cluster (who created what, when, from where). GKE provides audit logs via Cloud Logging by default.

```
AI DOCTOR EXAMPLE:
Application security for AI Doctor:
  - ANTHROPIC_API_KEY stored in K8s Secret (with etcd encryption)
  - TLS terminated at Ingress (cert-manager + Let's Encrypt)
  - CORS allows only the frontend domain
  - FastAPI validates all inputs via Pydantic models
  - Logs contain patient_id only, never names, DOB, or medical data
  - GKE audit logs track all kubectl operations
```

---

## 11. Security Checklist for AI Doctor

| # | Security Measure | Layer | Where | Priority |
|---|---|---|---|---|
| 1 | Enable private cluster | Infrastructure | GKE cluster config | Must-have |
| 2 | Restrict IAM roles (least privilege) | Infrastructure | GCP IAM | Must-have |
| 3 | Enable Workload Identity | Infrastructure | GKE + GCP SA | Must-have |
| 4 | Node auto-upgrade enabled | Infrastructure | GKE node pool config | Must-have |
| 5 | Shielded nodes enabled | Infrastructure | GKE node pool config | Nice-to-have |
| 6 | Dedicated ServiceAccounts per app | RBAC | K8s manifests | Must-have |
| 7 | Role with minimal permissions | RBAC | K8s manifests | Must-have |
| 8 | No cluster-admin for workloads | RBAC | K8s manifests | Must-have |
| 9 | Default deny NetworkPolicy | Network | K8s manifests | Must-have |
| 10 | Only backend can reach postgres | Network | NetworkPolicy | Must-have |
| 11 | Only Ingress can reach frontend/backend | Network | NetworkPolicy | Must-have |
| 12 | Backend egress limited to HTTPS + postgres | Network | NetworkPolicy | Nice-to-have |
| 13 | runAsNonRoot on all pods | Pod | Deployment securityContext | Must-have |
| 14 | readOnlyRootFilesystem | Pod | Deployment securityContext | Must-have |
| 15 | Drop all capabilities | Pod | Deployment securityContext | Must-have |
| 16 | Resource limits on all pods | Pod | Deployment resources | Must-have |
| 17 | Images from Artifact Registry only | Pod | Deployment image field | Must-have |
| 18 | Restricted Pod Security Standard | Pod | Namespace label | Nice-to-have |
| 19 | etcd encryption for Secrets | Application | GKE cluster config | Must-have |
| 20 | TLS via cert-manager | Application | Ingress + ClusterIssuer | Must-have |
| 21 | CORS restricted to frontend domain | Application | FastAPI middleware or Ingress | Must-have |
| 22 | No patient data in logs | Application | Application code | Must-have |
| 23 | Pydantic input validation | Application | FastAPI route handlers | Must-have |
| 24 | External Secrets Operator | Application | K8s + GCP Secret Manager | Nice-to-have |
| 25 | Image vulnerability scanning | Pod | Artifact Registry | Nice-to-have |

---

## Part 3: Service Discovery and Networking

---

## 12. The Problem Service Discovery Solves

### Pods Are Ephemeral

In Kubernetes, pods come and go constantly. A pod crashes and is replaced. A deployment is updated and old pods are terminated, new ones created. The scheduler moves pods to different nodes. Every time a pod is recreated, it gets a **new IP address**.

If your backend connects to PostgreSQL at `10.1.2.47:5432`, what happens when the PostgreSQL pod restarts and gets IP `10.1.3.89`? The backend is now connecting to an IP that no longer exists. Connection fails.

### The Problem Scales

With multiple replicas, the problem gets worse. You have 3 backend pods:

```
backend-abc123  →  10.1.2.10
backend-def456  →  10.1.2.11
backend-ghi789  →  10.1.2.12
```

The Ingress controller needs to forward requests to all three. If `backend-def456` is rescheduled, it gets IP `10.1.3.50`. Someone needs to update the Ingress controller's routing table. Manually tracking IPs across dozens of pods is not feasible.

### Pre-Kubernetes Solutions

Before Kubernetes, service discovery was an explicit problem that required a separate tool:

| Tool | How It Works | Complexity |
|---|---|---|
| **Hardcoded IPs** | Config file with IP addresses. Updated manually. | Low, but breaks on any change |
| **DNS round-robin** | Multiple A records for a hostname. Client picks one. | Medium, but stale records cause failures |
| **Consul** (HashiCorp) | Service registry + health checks + DNS interface | High, separate infrastructure to manage |
| **Eureka** (Netflix) | Java-based service registry (Spring Cloud) | High, JVM-centric |
| **ZooKeeper** (Apache) | Distributed coordination service | Very high, operationally complex |

### K8s Solution: Built-In Service Discovery

Kubernetes solves service discovery with two built-in mechanisms:

1. **Services:** A stable virtual IP (ClusterIP) and DNS name in front of a set of pods
2. **CoreDNS:** A DNS server running inside the cluster that automatically creates DNS records for every Service

You never hardcode IPs. You never run Consul or ZooKeeper. You create a Service, and every pod in the cluster can find it by name.

---

## 13. How K8s DNS Works

### CoreDNS

CoreDNS runs as a Deployment in the `kube-system` namespace. It is automatically installed in every Kubernetes cluster. It watches the Kubernetes API for Service objects and creates DNS records for each one.

```bash
kubectl get pods -n kube-system -l k8s-app=kube-dns
# coredns-5d78c9869d-abc12   1/1   Running
# coredns-5d78c9869d-def34   1/1   Running
```

### DNS Naming Convention

Every Service gets a DNS record in this format:

```
<service-name>.<namespace>.svc.cluster.local
```

For the AI Doctor Assistant:

| Service | Full DNS Name |
|---|---|
| Backend Service | `backend-service.doctor-app.svc.cluster.local` |
| Frontend Service | `frontend-service.doctor-app.svc.cluster.local` |
| PostgreSQL Service | `postgres-service.doctor-app.svc.cluster.local` |

### Short Names

Within the **same namespace**, you can use just the service name. Kubernetes configures each pod's `/etc/resolv.conf` with search domains:

```
# Inside a pod in the doctor-app namespace:
search doctor-app.svc.cluster.local svc.cluster.local cluster.local
nameserver 10.96.0.10
```

This means:
- `postgres-service` resolves to `postgres-service.doctor-app.svc.cluster.local`
- No need to type the full DNS name within the same namespace

### How Resolution Works

Here is the full chain from a backend pod connecting to PostgreSQL:

```
┌────────────────────────┐
│  Backend Pod            │
│                         │
│  Code: connect to       │
│  "postgres-service:5432"│
└───────────┬─────────────┘
            │
            │ 1. DNS query: "postgres-service"
            ▼
┌────────────────────────┐
│  CoreDNS Pod            │
│  (kube-system namespace)│
│                         │
│  Resolves:              │
│  postgres-service       │
│  → 10.96.45.12         │  ← This is the ClusterIP (virtual IP)
│  (ClusterIP of the     │
│   postgres Service)     │
└───────────┬─────────────┘
            │
            │ 2. Connection to ClusterIP 10.96.45.12:5432
            ▼
┌────────────────────────┐
│  kube-proxy / iptables  │
│  (on the node)          │
│                         │
│  NAT translation:       │
│  10.96.45.12:5432       │
│  → 10.1.2.47:5432      │  ← Actual pod IP
└───────────┬─────────────┘
            │
            │ 3. Packet delivered to actual pod
            ▼
┌────────────────────────┐
│  PostgreSQL Pod         │
│  IP: 10.1.2.47          │
│  Port: 5432             │
└─────────────────────────┘
```

The backend code just says `postgres-service:5432`. It never knows (or cares about) the actual pod IP. If the PostgreSQL pod restarts with a new IP, CoreDNS still resolves `postgres-service` to the same ClusterIP, and kube-proxy updates its routing rules to point to the new pod IP. The backend connection string never changes.

---

## 14. Service Types and When to Use Each

Kubernetes has five Service types. Each solves a different networking problem.

### ClusterIP (Default)

**What it does:** Creates a virtual IP accessible only from within the cluster. Pods can reach this IP, but nothing outside the cluster can.

**When to use:** For communication between services inside the cluster. This is the default and most common type.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: doctor-app
spec:
  type: ClusterIP          # Default, can be omitted
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
```

```
AI DOCTOR: PostgreSQL Service is ClusterIP. Only backend pods need
to reach it. No external access required.
```

### NodePort

**What it does:** Exposes the Service on a static port on every node's IP. External traffic can reach the Service via `<NodeIP>:<NodePort>`.

**When to use:** Development and testing. Quick external access without a load balancer. Not recommended for production (exposes node IPs, limited port range 30000-32767).

```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend-nodeport
  namespace: doctor-app
spec:
  type: NodePort
  selector:
    app: backend
  ports:
    - port: 8000
      targetPort: 8000
      nodePort: 30080      # Access via <any-node-ip>:30080
```

```
AI DOCTOR: NodePort for quick testing on minikube. Access the backend
at http://$(minikube ip):30080/health
```

### LoadBalancer

**What it does:** Provisions a cloud load balancer (GCP, AWS, Azure) that forwards traffic to the Service. Gets a public external IP automatically.

**When to use:** When you need direct external access to a single Service. Each LoadBalancer Service creates a separate cloud load balancer (which costs money).

```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend-lb
  namespace: doctor-app
spec:
  type: LoadBalancer
  selector:
    app: backend
  ports:
    - port: 80
      targetPort: 8000
```

```
AI DOCTOR: We use Ingress instead of LoadBalancer Services. Ingress
consolidates routing for multiple services behind a single load
balancer, saving cost and complexity.
```

### ExternalName

**What it does:** Maps a Service to an external DNS name. It is a CNAME alias, not a proxy. The cluster DNS returns the external DNS name, and the client resolves and connects directly.

**When to use:** When a service lives outside the cluster (managed database, external API) and you want to reference it by a Kubernetes Service name.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: external-db
  namespace: doctor-app
spec:
  type: ExternalName
  externalName: my-db-instance.us-central1.cloudsql.gcp.example.com
```

```
AI DOCTOR: If we migrated PostgreSQL to Cloud SQL, we would use an
ExternalName Service so the backend still connects to
"external-db.doctor-app.svc" without code changes.
```

### Headless Service (clusterIP: None)

**What it does:** Instead of a virtual ClusterIP, DNS returns the actual pod IPs directly. Clients connect to individual pods, not through a load-balanced virtual IP.

**When to use:** StatefulSets (databases) where clients need stable, direct pod connections. Each pod in a StatefulSet gets a predictable DNS name: `<pod-name>.<service-name>.<namespace>.svc.cluster.local`.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: doctor-app
spec:
  clusterIP: None         # Headless
  selector:
    app: postgres
  ports:
    - port: 5432
```

```
AI DOCTOR: PostgreSQL runs as a StatefulSet with a headless Service.
The pod gets a stable DNS name: postgres-0.postgres.doctor-app.svc
This name persists across pod restarts, which is critical for
database replication and connection management.
```

### Comparison Table

| Type | External Access | Use Case (AI Doctor) | Creates Cloud LB | Cost |
|---|---|---|---|---|
| **ClusterIP** | No (internal only) | PostgreSQL, inter-service calls | No | Free |
| **NodePort** | Yes (via node IP:port) | Local dev testing | No | Free |
| **LoadBalancer** | Yes (external IP) | Direct public access to one service | Yes | $$$ |
| **ExternalName** | N/A (DNS alias) | Cloud SQL, external APIs | No | Free |
| **Headless** | No (internal only) | StatefulSets, databases | No | Free |

---

## 15. How Microservices Find Each Other

### Using Service DNS Names (Recommended)

The standard approach: call other services by their DNS name. This works across namespaces and is the idiomatic Kubernetes way.

**Python (backend calling PostgreSQL):**

```python
# backend/src/config.py
import os

# Service DNS name — works because both are in doctor-app namespace
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://doctor:password@postgres-service:5432/doctor_db"
)
#                                         ^^^^^^^^^^^^^^^^
#                                         K8s Service name (short form)
```

**Python (httpx calling another internal service):**

```python
import httpx

# If you had a separate notification service in the same namespace:
async def send_notification(patient_id: str, message: str) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://notification-service:8080/notify",
            #      ^^^^^^^^^^^^^^^^^^^^
            #      K8s Service DNS name
            json={"patient_id": patient_id, "message": message},
        )
        response.raise_for_status()
```

**TypeScript (fetch calling another internal service):**

```typescript
// If the frontend needed to call the backend from a server-side context:
const response = await fetch(
  "http://backend-service.doctor-app.svc.cluster.local:8000/api/patients",
  //     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  //     Full K8s DNS name (needed when calling across namespaces)
  {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  }
);
```

### Environment Variables (Legacy Approach)

Kubernetes automatically injects environment variables for each Service into every pod:

```bash
# Inside any pod in the doctor-app namespace:
echo $POSTGRES_SERVICE_SERVICE_HOST    # 10.96.45.12
echo $POSTGRES_SERVICE_SERVICE_PORT    # 5432
echo $BACKEND_SERVICE_SERVICE_HOST     # 10.96.78.34
echo $BACKEND_SERVICE_SERVICE_PORT     # 8000
```

**Why this is not recommended:** Environment variables are set at pod creation time. If a Service is created after the pod, the environment variables are missing. DNS-based discovery works regardless of creation order.

### AI Doctor Service Communication

```
AI DOCTOR EXAMPLE:
Frontend pods (nginx): Do NOT call the backend directly.
  The browser makes requests to the Ingress, which routes
  /api/* to the backend Service. Frontend pods serve static
  files only.

Backend pods (FastAPI): Call two things:
  1. postgres-service:5432 — Kubernetes ClusterIP Service
     (same namespace, short name works)
  2. api.anthropic.com:443 — External API (Claude)
     (egress goes through the node's internet connection)

PostgreSQL pods: Do not initiate connections to anything.
  They listen on 5432 and accept connections from backend pods.
```

---

## 16. Ingress vs Service vs Pod Networking

Kubernetes has three layers of networking. Each operates at a different scope.

### Pod Networking

Every pod gets a unique IP address within the cluster. Pods can reach each other directly by IP, even across nodes. This is the **flat network** mentioned in the security section.

```
Node 1                          Node 2
┌────────────────────┐         ┌────────────────────┐
│ Pod A: 10.1.2.10   │────────►│ Pod C: 10.1.3.20   │
│ Pod B: 10.1.2.11   │◄────────│ Pod D: 10.1.3.21   │
└────────────────────┘         └────────────────────┘
     Direct pod-to-pod communication across nodes
     (CNI plugin handles cross-node routing)
```

### Service Networking

Services provide a stable virtual IP (ClusterIP) and DNS name in front of a set of pods. kube-proxy (running on each node) handles the translation from ClusterIP to actual pod IPs via iptables or IPVS rules.

```
             ┌─────────────────────────────────────┐
             │  backend-service (ClusterIP)          │
             │  IP: 10.96.78.34                      │
             │  Port: 8000                           │
             │                                       │
             │  Load balances across:                │
             │  ┌───────────┐  ┌───────────┐        │
             │  │ Pod 1     │  │ Pod 2     │        │
             │  │ 10.1.2.10 │  │ 10.1.3.20 │        │
             │  │ :8000     │  │ :8000     │        │
             │  └───────────┘  └───────────┘        │
             └─────────────────────────────────────┘
```

### Ingress Networking

Ingress operates at Layer 7 (HTTP). It receives external HTTP requests and routes them to the correct Service based on host and path rules.

```
Internet (HTTPS)
      │
      ▼
┌──────────────────────────────────────┐
│  Cloud Load Balancer                   │
│  (provisioned by Ingress controller)  │
└───────────────┬──────────────────────┘
                │
                ▼
┌──────────────────────────────────────┐
│  Ingress Controller Pods              │
│  (or GCE LB in GKE)                  │
│                                       │
│  Rules:                               │
│  doctor-app.example.com/* → frontend  │
│  doctor-app.example.com/api/* → backend│
└───────┬───────────────────┬──────────┘
        │                   │
        ▼                   ▼
  frontend-service    backend-service
  (ClusterIP)         (ClusterIP)
        │                   │
        ▼                   ▼
  frontend pods       backend pods
```

### All Three Layers Together

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  LAYER 3: INGRESS (external HTTP routing)                              │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ Cloud LB → Ingress Controller → path-based routing to Services  │ │
│  └──────────────────────────────────┬───────────────────────────────┘ │
│                                      │                                 │
│  LAYER 2: SERVICES (stable internal endpoints)                         │
│  ┌──────────────────────────────────┼───────────────────────────────┐ │
│  │ ClusterIP: 10.96.x.x             │  DNS: svc.cluster.local       │ │
│  │ Load balances across pod replicas │  kube-proxy handles routing   │ │
│  └──────────────────────────────────┼───────────────────────────────┘ │
│                                      │                                 │
│  LAYER 1: POD NETWORKING (flat network, unique IPs)                    │
│  ┌──────────────────────────────────┼───────────────────────────────┐ │
│  │ Every pod: unique IP (10.1.x.x)  │  Cross-node via CNI plugin    │ │
│  │ Direct pod-to-pod possible        │  NetworkPolicies restrict     │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Full Request Lifecycle

Here is every step when a user loads the AI Doctor app:

```
1. Browser types: https://doctor-app.example.com/
2. DNS resolves doctor-app.example.com → Cloud LB external IP (e.g., 34.120.1.1)
3. Browser sends HTTPS request to 34.120.1.1:443
4. Cloud Load Balancer receives the request
5. Ingress Controller terminates TLS (HTTPS → HTTP)
6. Ingress Controller matches path "/" → frontend-service
7. frontend-service (ClusterIP 10.96.10.5) selected
8. kube-proxy translates 10.96.10.5 → 10.1.2.10 (frontend pod IP)
9. Request arrives at frontend pod → nginx serves index.html
10. Browser loads JavaScript, makes POST /api/briefings
11. Same path: Cloud LB → Ingress → matches "/api" → backend-service
12. kube-proxy routes to backend pod (10.1.3.20)
13. uvicorn/FastAPI handles the request
14. FastAPI calls postgres-service:5432 → CoreDNS → kube-proxy → PostgreSQL pod
15. FastAPI calls api.anthropic.com:443 (external, via node's internet)
16. FastAPI returns JSON response back through the chain
```

---

## 17. When Services Are Not Enough: Service Mesh

A **service mesh** adds a sidecar proxy (typically Envoy) to every pod. All traffic between pods flows through these proxies, which provides:

- **Mutual TLS (mTLS):** Encrypted, authenticated communication between all services automatically
- **Traffic management:** Canary deployments, traffic splitting, retries, circuit breaking
- **Observability:** Distributed tracing, request metrics, service graphs without code changes

The two most popular service meshes are **Istio** (feature-rich, complex) and **Linkerd** (lightweight, simpler).

**When you need a service mesh:**
- Dozens of microservices communicating in complex patterns
- Regulatory requirement for encryption between all services
- Need for advanced traffic management (canary releases with traffic percentage split)
- Requirement for distributed tracing without modifying application code

**When you do NOT need a service mesh:**
- Fewer than 10 services
- NetworkPolicies provide sufficient security
- You can add tracing via application-level libraries
- The operational complexity of a service mesh outweighs the benefits

```
AI DOCTOR EXAMPLE:
AI Doctor has 3 services. A service mesh would add a sidecar proxy
to every pod, increasing memory usage, latency, and operational
complexity for negligible benefit.

NetworkPolicies + K8s Secrets + Ingress TLS provide adequate security.
If AI Doctor grew to 20+ microservices with strict compliance
requirements, a service mesh would become worth considering.
```

---

## Part 4: Deployment Comparison

---

## 18. Where to Deploy Different Types of Apps

Not every application should run on Kubernetes. Here is a guide for matching workload types to deployment platforms.

### Workload Comparison Table

| Workload | Best Platform | Why | K8s Suitable? |
|---|---|---|---|
| **Static site / marketing page** | CDN (Cloudflare Pages, Vercel, Netlify) | No server needed, global edge caching | Overkill |
| **REST API (low traffic)** | VPS + docker-compose, or Cloud Run | Simple, cheap, auto-scales to zero | Works but expensive for low traffic |
| **REST API (high traffic)** | Kubernetes or Cloud Run | Need scaling, rolling updates, health checks | Yes, ideal use case |
| **Real-time chat / WebSocket** | Kubernetes or dedicated servers | Need persistent connections, sticky sessions | Yes, with proper config |
| **ML model inference** | Kubernetes (GPU nodes) or dedicated GPU VMs | Need GPU scheduling, model versioning | Yes, K8s excels at GPU scheduling |
| **Cron job / scheduled task** | Kubernetes CronJob, or Cloud Scheduler + Cloud Run | Needs reliable scheduling and retry | Yes, CronJob is built for this |
| **Background worker / queue consumer** | Kubernetes Deployment or Cloud Run Jobs | Long-running, needs scaling with queue depth | Yes |
| **Serverless function** | Cloudflare Workers, AWS Lambda, Cloud Functions | Stateless, bursty, <30s execution | No, K8s pods are too heavy |
| **Database** | Managed service (Cloud SQL, RDS) or K8s StatefulSet | Needs persistence, backups, replication | Yes, but managed is easier |
| **Full-stack web app** | Kubernetes, VPS, or PaaS (Railway, Render) | Multiple services, needs orchestration | Yes, if complexity is justified |

### Platform Comparison

| Feature | VPS ($5-20/mo) | Cloud Run | Kubernetes (GKE) | Workers/Lambda | PaaS (Railway) |
|---|---|---|---|---|---|
| **Startup time** | Always running | 0-10 seconds (cold start) | 5-30 seconds (new pod) | <50ms (edge) | Always running |
| **Scale to zero** | No | Yes | No (min 1 pod) | Yes | No |
| **Auto-scaling** | No | Yes (built-in) | Yes (HPA) | Yes (automatic) | Limited |
| **GPU support** | Manual setup | Limited | Yes (GPU node pools) | No | No |
| **Persistent storage** | Yes (disk) | No (stateless) | Yes (PV/PVC) | No | Limited |
| **Custom networking** | Full control | Limited | Full control (Services, NetworkPolicy) | None | None |
| **Deployment complexity** | Low (SSH + git pull) | Low (gcloud deploy) | High (YAML manifests) | Low (wrangler deploy) | Low (git push) |
| **Operational overhead** | High (you manage everything) | Low (managed) | Medium (managed control plane) | Very low | Very low |
| **Cost at low traffic** | $5-20/mo (always on) | ~$0 (scale to zero) | $70-200+/mo (cluster fees) | ~$0 (pay per request) | $5-20/mo |
| **Cost at high traffic** | Cheap (fixed price) | Moderate (per-request) | Moderate (predictable) | Can be expensive | Moderate |
| **Max request duration** | Unlimited | 60 minutes | Unlimited | 30s (Workers) / 15min (Lambda) | Varies |
| **WebSocket support** | Yes | Yes (limited) | Yes | Limited | Yes |
| **Team collaboration** | Low (shared SSH) | Good (IAM) | Excellent (RBAC, namespaces) | Good (IAM) | Good |
| **Learning value** | Linux sysadmin | Serverless patterns | Container orchestration | Edge computing | None (abstracted) |

### Where AI Doctor Fits

```
AI DOCTOR EXAMPLE:
AI Doctor is a full-stack web app with 3 services. Here is where
it could run, ranked from simplest to most complex:

1. SIMPLEST: VPS with docker-compose ($10/month)
   - docker-compose up on a DigitalOcean Droplet
   - nginx for TLS and routing
   - Works perfectly at current scale
   - No auto-scaling, manual deploys

2. MODERATE: Google Cloud Run (~$5-30/month)
   - Backend and frontend as Cloud Run services
   - Cloud SQL for PostgreSQL
   - Auto-scales to zero when not in use
   - Managed TLS, no infrastructure to manage

3. LEARNING PATH: GKE Autopilot (~$75-150/month)
   - Full Kubernetes deployment
   - Auto-scaling, rolling updates, RBAC, NetworkPolicies
   - Transferable skills for any K8s-based project
   - Significant learning investment

4. OVERKILL: Multi-cluster K8s with service mesh
   - Istio, multi-region, blue-green deployments
   - For enterprise-scale medical platforms, not a learning project

We use option 3 because the goal is learning Kubernetes, not
minimizing cost. For a production medical app at scale, option 3
is the right technical choice. At current learning-project scale,
option 1 or 2 would be more practical.
```

---

## 19. Summary

### Key Takeaways

**Why Kubernetes:**
- Kubernetes solves real problems: self-healing, scaling, rolling updates, configuration management
- But it introduces significant complexity. Match the tool to the problem.
- For AI Doctor, K8s is a learning investment. The skills transfer to any production system.
- A VPS with docker-compose would work fine at current scale. Be honest about tradeoffs.

**Security is five layers, not one setting:**

```
┌───────────────────────────────────────────────────────────┐
│  Layer 1: Cloud/Infrastructure                             │
│    IAM, private cluster, Workload Identity, node security  │
│                                                           │
│  Layer 2: Kubernetes RBAC                                  │
│    ServiceAccounts, Roles, RoleBindings, least privilege   │
│                                                           │
│  Layer 3: Network Security                                 │
│    NetworkPolicies (default deny, allow selectively)       │
│                                                           │
│  Layer 4: Pod Security                                     │
│    Non-root, read-only FS, drop capabilities, limits       │
│                                                           │
│  Layer 5: Application Security                             │
│    Secrets management, TLS, CORS, no patient data in logs  │
└───────────────────────────────────────────────────────────┘
```

**Service discovery is built-in, not hardcoded:**
- CoreDNS creates DNS records for every Service automatically
- Use `<service-name>` within the same namespace
- Use `<service-name>.<namespace>.svc.cluster.local` across namespaces
- Never hardcode pod IPs. Services abstract pod lifecycle away.

**Full AI Doctor Architecture with Security and Discovery:**

```
┌───────────────────────────────────────────────────────────────────────┐
│                        GKE Autopilot Cluster                           │
│                        (private, auto-upgrading nodes)                 │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Namespace: doctor-app                                           │ │
│  │  Pod Security Standard: restricted                               │ │
│  │  Default NetworkPolicy: deny all ingress                         │ │
│  │                                                                  │ │
│  │         Internet                                                 │ │
│  │            │                                                     │ │
│  │            ▼                                                     │ │
│  │  ┌──────────────────────┐                                       │ │
│  │  │  Ingress (TLS + routing)                                     │ │
│  │  └───────┬──────────┬───┘                                       │ │
│  │          │          │                                            │ │
│  │    /*    │    /api/* │                                           │ │
│  │          ▼          ▼                                            │ │
│  │  ┌────────────┐  ┌────────────┐                                 │ │
│  │  │ frontend   │  │ backend    │──► api.anthropic.com (HTTPS)    │ │
│  │  │ Service    │  │ Service    │                                  │ │
│  │  │ ClusterIP  │  │ ClusterIP  │                                  │ │
│  │  └─────┬──────┘  └─────┬──────┘                                 │ │
│  │        │               │                                         │ │
│  │   ┌────┴────┐     ┌────┴────┐                                   │ │
│  │   │ nginx   │     │uvicorn  │                                   │ │
│  │   │ pod x2  │     │ pod x2  │                                   │ │
│  │   │ non-root│     │ non-root│                                   │ │
│  │   │ RO fs   │     │ RO fs   │                                   │ │
│  │   └─────────┘     └────┬────┘                                   │ │
│  │                        │                                         │ │
│  │                        │ postgres-service:5432 (DNS discovery)   │ │
│  │                        ▼                                         │ │
│  │                  ┌───────────┐                                   │ │
│  │                  │ PostgreSQL│                                   │ │
│  │                  │ pod x1    │                                   │ │
│  │                  │ non-root  │                                   │ │
│  │                  │ PVC: 20Gi │                                   │ │
│  │                  └───────────┘                                   │ │
│  │                                                                  │ │
│  │  RBAC: backend-sa can read Secrets in doctor-app only            │ │
│  │  NetworkPolicy: postgres accepts only from backend               │ │
│  │  Secrets: ANTHROPIC_API_KEY, DATABASE_PASSWORD (etcd encrypted)  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  Workload Identity: backend-sa → GCP SA (secretmanager.accessor)      │
│  IAM: Private cluster, authorized networks only                       │
│  Nodes: COS images, shielded, auto-upgrade, auto-repair              │
└───────────────────────────────────────────────────────────────────────┘
```

### What to Remember

1. **K8s is not always the answer.** Match the tool to the problem. A $10 VPS solves many problems that K8s solves, just not as elegantly.
2. **Security is layered.** Five independent layers, each catching what the previous one misses. Start with the must-haves from the checklist.
3. **Service discovery is built-in.** Use DNS names, not IP addresses. CoreDNS handles everything automatically.
4. **NetworkPolicies are critical.** The default flat network is the most dangerous default in Kubernetes. Always start with deny-all and allow selectively.
5. **Pod security is non-negotiable.** Non-root, read-only filesystem, drop all capabilities. These are simple settings that prevent entire classes of exploits.

---

> **Next:** [12-DEPLOYING-ALONGSIDE-PORTFOLIO.md](./12-DEPLOYING-ALONGSIDE-PORTFOLIO.md) applies everything from this series to a real-world deployment scenario — deploying AI Doctor alongside a portfolio site and understanding how managed databases work internally. Return to [00-OVERVIEW.md](./00-OVERVIEW.md) for the full series index, or revisit [08-KNOWLEDGE-CHECK.md](./08-KNOWLEDGE-CHECK.md) to test your understanding of security, service discovery, and deployment platform selection.