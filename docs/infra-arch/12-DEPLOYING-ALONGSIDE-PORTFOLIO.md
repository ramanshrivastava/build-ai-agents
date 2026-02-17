# Deploying Alongside a Portfolio + Managed Database Internals

> **Document 12 of 12** in the [Infrastructure & Kubernetes Learning Guide](./00-OVERVIEW.md)
>
> **Purpose:** Answer two practical questions that arise after completing the series: (1) How do you deploy AI Doctor alongside an existing portfolio site so visitors can experience it live? (2) Do managed databases (PostgreSQL, MongoDB, Redis) actually run on Kubernetes internally, or something else? The first question grounds everything from docs 01-11 into a real deployment decision. The second demystifies what "managed" actually means under the hood.
>
> **Prerequisites:** Documents 01-06 (core K8s, GKE, tooling, app mapping, CI/CD), Document 10 (nginx, Ingress), Document 11 (security, discovery, deployment comparison). You should understand DNS, TLS, containers, Kubernetes Services, and the AI Doctor architecture (FastAPI + React + PostgreSQL).

---

## Table of Contents

### Part 1: Deploying AI Doctor Alongside Your Portfolio
1. [The Scenario](#1-the-scenario)
2. [Three Approaches to Coexistence](#2-three-approaches-to-coexistence)
3. [Subdomain Architecture](#3-subdomain-architecture)
4. [Choosing the Right Deployment Target](#4-choosing-the-right-deployment-target)
5. [The Portfolio Integration Pattern](#5-the-portfolio-integration-pattern)

### Part 2: How Managed Databases Actually Work
6. [The Two Planes](#6-the-two-planes)
7. [Why NOT Kubernetes for Databases](#7-why-not-kubernetes-for-databases)
8. [Managed PostgreSQL Internals](#8-managed-postgresql-internals)
9. [Managed MongoDB Internals](#9-managed-mongodb-internals)
10. [Managed Redis Internals](#10-managed-redis-internals)
11. [The Pattern: Data Plane on VMs, Control Plane Varies](#11-the-pattern-data-plane-on-vms-control-plane-varies)

### Part 3: Putting It Together
12. [AI Doctor Deployment Plan](#12-ai-doctor-deployment-plan)
13. [Summary](#13-summary)

---

## Part 1: Deploying AI Doctor Alongside Your Portfolio

You have been studying Kubernetes, containers, networking, security, and deployment platforms across eleven documents. Now comes the question that turns all of that knowledge into action: **how do you actually put this application on the internet, next to a portfolio site that already exists?**

This is not a hypothetical scenario. It is the exact situation most developers face when they build a project worth showing.

---

## 1. The Scenario

### What Already Exists

You have a portfolio website running on Vercel. The site is a Next.js application. It serves at `ramanshrivastava.com`. Vercel handles everything: builds the app, serves it on a global CDN, manages TLS certificates, provides the DNS integration. You do not manage any servers for this site.

```
Current State
─────────────

   Browser                        Vercel CDN (Edge)
     │                                  │
     │  GET ramanshrivastava.com        │
     │ ─────────────────────────────►   │
     │                                  │  Serves Next.js static + SSR
     │  ◄─────────────────────────────  │
     │  HTML/CSS/JS                     │
     │                                  │

   DNS: ramanshrivastava.com → Vercel (CNAME to cname.vercel-dns.com)
   TLS: Automatic via Vercel
   Cost: $0 (hobby tier)
```

### What You Want to Add

AI Doctor Assistant is a full-stack application with three services:

1. **React frontend** — static files served by nginx
2. **FastAPI backend** — Python application server connecting to Claude API
3. **PostgreSQL database** — persistent data storage

You want visitors to your portfolio to be able to try AI Doctor as a live demo. The question is: how do you add a multi-service application alongside a static portfolio without breaking anything?

### Why This Question Matters

This is not a toy problem. It is the deployment decision that **every developer** faces when transitioning from "I built a thing" to "people can use the thing." The answer involves DNS, TLS, cost management, architecture choices, and operational tradeoffs that draw on nearly every topic from this series.

```
What We Want
────────────

   ramanshrivastava.com          →  Portfolio (Vercel)
   doctor.ramanshrivastava.com   →  AI Doctor (somewhere else)

   Same domain, different subdomains, different hosting platforms.
```

---

## 2. Three Approaches to Coexistence

There are three realistic ways to serve AI Doctor alongside an existing portfolio. Each involves fundamentally different DNS, routing, and operational tradeoffs.

### Approach A: Subdomain

The portfolio stays at the apex domain (`ramanshrivastava.com`). AI Doctor lives on a subdomain (`doctor.ramanshrivastava.com`). Each domain points to a completely different hosting platform. They share a parent domain but are otherwise independent.

```
Approach A: Subdomain
─────────────────────

  ramanshrivastava.com
  │
  ├── ramanshrivastava.com           → Vercel  (portfolio)
  │     DNS: CNAME → cname.vercel-dns.com
  │
  └── doctor.ramanshrivastava.com    → Cloud Run / VPS / GKE  (AI Doctor)
        DNS: CNAME → your-deployment-target

  Two completely independent deployments.
  Each manages its own TLS certificate.
  No routing overlap. No proxy chains.
```

### Approach B: Path Rewrite

Everything lives under the same domain. The portfolio at `/`, AI Doctor at `/doctor`. Vercel proxies requests that match `/doctor/*` to wherever AI Doctor is hosted.

```
Approach B: Path Rewrite
────────────────────────

  ramanshrivastava.com
  │
  ├── ramanshrivastava.com/*          → Vercel (portfolio)
  │
  └── ramanshrivastava.com/doctor/*   → Vercel rewrites to external backend
        vercel.json: { "rewrites": [{ "source": "/doctor/:path*",
                                       "destination": "https://doctor-backend.example.com/:path*" }]}

  Single domain. Vercel acts as reverse proxy for /doctor paths.
  AI Doctor must handle being served at /doctor/ prefix.
```

### Approach C: Link Only

AI Doctor lives on a completely separate domain (e.g., `ai-doctor-demo.com` or a free PaaS subdomain like `ai-doctor.fly.dev`). The portfolio links to it like any external project.

```
Approach C: Link Only
─────────────────────

  ramanshrivastava.com              → Vercel (portfolio)
    └── "View live demo" link to → ai-doctor-demo.fly.dev

  No DNS configuration. No routing.
  Just a hyperlink from your portfolio to the app.
```

### Comparison Table

| Factor | A: Subdomain | B: Path Rewrite | C: Link Only |
|---|---|---|---|
| **Professional appearance** | `doctor.ramanshrivastava.com` looks polished | `/doctor` looks integrated | External domain looks less professional |
| **DNS complexity** | One CNAME record | None (Vercel handles routing) | None |
| **Routing complexity** | None (separate deployments) | Vercel rewrite rules + path prefix handling | None |
| **TLS** | Separate cert for subdomain | Vercel handles everything | Separate cert or platform-provided |
| **Frontend path handling** | App served at `/` (normal) | App must handle `/doctor` prefix in all routes | App served at `/` (normal) |
| **Backend CORS** | `doctor.ramanshrivastava.com` | `ramanshrivastava.com` | External domain |
| **Independence** | Full (separate deploys, separate failures) | Coupled (Vercel rewrite failure breaks app) | Full |
| **Portfolio downtime affects app?** | No | Yes (proxy layer is Vercel) | No |
| **Cost** | Same as standalone deployment | Same + Vercel proxy overhead | Same as standalone deployment |
| **Effort** | Low (one DNS record) | Medium (rewrite config + path prefix headache) | Lowest |

### Recommendation: Subdomain (Approach A)

The subdomain approach wins for several reasons:

1. **No path prefix headaches.** React Router, FastAPI, and every other framework assumes the app is served at `/`. Adding a path prefix (`/doctor`) requires configuration changes in the frontend build, backend CORS, API base URLs, and static asset paths. It is a recurring source of bugs.

2. **Complete isolation.** Your portfolio and AI Doctor share nothing except a parent domain. Deploying, scaling, or crashing one has zero effect on the other.

3. **Professional appearance.** `doctor.ramanshrivastava.com` communicates that this is a real project, not a toy hidden under a portfolio subfolder.

4. **Simple DNS.** One CNAME record. That is the total infrastructure change to your existing setup.

5. **Standard pattern.** This is how companies deploy multiple services: `api.company.com`, `docs.company.com`, `app.company.com`. You are learning the production pattern, not a shortcut.

---

## 3. Subdomain Architecture

### DNS Routing

DNS is the foundation. Two DNS records route traffic to two completely different platforms:

```
DNS Configuration
─────────────────

  Domain Registrar / Cloudflare DNS Panel
  ┌──────────────────────────────────────────────────────────────┐
  │                                                              │
  │  Record Type   Name                  Target                  │
  │  ──────────── ──────────────────── ─────────────────────── │
  │  CNAME         ramanshrivastava.com  cname.vercel-dns.com   │
  │  CNAME         doctor                <deployment-target>     │
  │                                                              │
  │  (or if using Cloudflare as DNS + proxy:)                    │
  │  A             ramanshrivastava.com  76.76.21.21  (Vercel)  │
  │  CNAME         doctor                <deployment-target>     │
  └──────────────────────────────────────────────────────────────┘


  Request Flow
  ────────────

  Browser: ramanshrivastava.com
     │
     ▼
  DNS resolves → Vercel CDN
     │
     ▼
  Vercel serves Next.js portfolio


  Browser: doctor.ramanshrivastava.com
     │
     ▼
  DNS resolves → Cloud Run / VPS / GKE external IP
     │
     ▼
  Your deployment serves AI Doctor
```

### TLS for Subdomains

TLS certificates prove that your server legitimately owns the domain. There are three approaches for handling TLS across a parent domain and subdomains:

**Option 1: Per-subdomain certificates (simplest)**

Each platform gets its own certificate. Vercel auto-provisions a cert for `ramanshrivastava.com`. Your deployment target auto-provisions a cert for `doctor.ramanshrivastava.com`. Let's Encrypt supports this natively.

```
Per-Subdomain Certificates
──────────────────────────

  ramanshrivastava.com         → cert issued by Vercel (Let's Encrypt)
  doctor.ramanshrivastava.com  → cert issued by your platform:
                                  - Cloud Run: automatic Google-managed cert
                                  - VPS: certbot + Let's Encrypt
                                  - GKE: cert-manager + Let's Encrypt
                                  - Fly.io: automatic
                                  - Railway: automatic
```

This is the recommended approach. Each platform handles its own TLS. No coordination needed.

**Option 2: Wildcard certificate via Cloudflare**

If you use Cloudflare as your DNS provider with proxy enabled (orange cloud), Cloudflare provides a wildcard certificate (`*.ramanshrivastava.com`) at the edge. All subdomains are covered automatically. Traffic between Cloudflare and your origin server can use Cloudflare origin certificates or Let's Encrypt.

```
Cloudflare Wildcard
───────────────────

  Browser ──HTTPS──► Cloudflare Edge
                      │  TLS terminated here
                      │  Cert: *.ramanshrivastava.com
                      │
                      ├──► Vercel (portfolio)
                      │    Origin: HTTPS or Cloudflare origin cert
                      │
                      └──► Cloud Run / VPS (AI Doctor)
                           Origin: HTTPS or Cloudflare origin cert
```

**Option 3: Wildcard certificate via Let's Encrypt (advanced)**

You run `certbot` with a DNS-01 challenge to get a wildcard cert. This requires DNS API access and is more complex to automate. Only useful if you self-manage all TLS on a VPS.

**Recommendation:** Use Option 1 (per-subdomain) if your deployment platform auto-provisions certificates. Use Option 2 if you already use Cloudflare DNS. Option 3 is rarely necessary.

### The Complete DNS Setup (Step by Step)

Assuming Cloudflare as DNS provider (most common for developers):

```
Step 1: Verify Existing Portfolio DNS
──────────────────────────────────────
Your portfolio already works. Verify the existing record:

  Type    Name                      Target                  Proxy
  CNAME   ramanshrivastava.com      cname.vercel-dns.com   ON (orange cloud)

  (or A record pointing to Vercel IP, depending on setup)


Step 2: Add Subdomain Record
─────────────────────────────
Add one DNS record for the AI Doctor subdomain.

The target depends on your deployment choice (covered in section 4):

  If Cloud Run:
    CNAME   doctor   ghs.googlehosted.com     Proxy OFF (grey cloud)
    (Cloud Run custom domain mapping resolves to Google's servers)

  If VPS (DigitalOcean, Hetzner):
    A       doctor   203.0.113.42             Proxy ON or OFF
    (IP address of your VPS)

  If Fly.io:
    CNAME   doctor   doctor-app.fly.dev       Proxy OFF
    (Fly auto-provisions TLS via CNAME verification)

  If Railway:
    CNAME   doctor   <railway-provided-cname> Proxy OFF


Step 3: Verify
───────────────
After DNS propagation (usually 1-5 minutes with Cloudflare):

  $ dig doctor.ramanshrivastava.com +short
  # Should return the IP or CNAME of your deployment target

  $ curl -I https://doctor.ramanshrivastava.com
  # Should return HTTP 200 with valid TLS
```

---

## 4. Choosing the Right Deployment Target

Document 11 compared deployment platforms in the abstract. Now we apply that comparison to a specific scenario: hosting AI Doctor as a live portfolio demo.

### Decision Framework

The right platform depends on three factors for a portfolio demo:

1. **Cost sensitivity** — This is a showcase, not a revenue-generating product. Monthly cost matters.
2. **Operational burden** — You do not want to SSH into a server at 2am because your demo is down during a recruiter visit.
3. **Learning value** — Part of the point is demonstrating infrastructure skills.

### Option 1: Cloud Run + Cloud SQL

```
Cloud Run Architecture
──────────────────────

  doctor.ramanshrivastava.com
         │
         ▼
  ┌─────────────────────┐
  │  Google Cloud Run     │
  │                       │
  │  ┌─────────────────┐ │
  │  │  Frontend        │ │     ← Cloud Run service #1
  │  │  (nginx + React) │ │       Container: nginx serving static build
  │  └────────┬────────┘ │       Scale: 0-2 instances
  │           │           │
  │  Browser calls /api/* │
  │           │           │
  │  ┌────────▼────────┐ │
  │  │  Backend         │ │     ← Cloud Run service #2
  │  │  (FastAPI)       │ │       Container: uvicorn + FastAPI
  │  │                  │──────► Claude API (api.anthropic.com)
  │  └────────┬────────┘ │       Scale: 0-2 instances
  │           │           │
  └───────────┼───────────┘
              │
              │  Cloud SQL Proxy (sidecar or Auth Proxy)
              ▼
  ┌─────────────────────┐
  │  Cloud SQL           │       ← Managed PostgreSQL
  │  (PostgreSQL 16)     │         Smallest tier: db-f1-micro
  │  Private IP          │         Automatic backups
  └─────────────────────┘

  Estimated Cost: $10-25/month
    Cloud Run: ~$0-5 (scales to zero, free tier covers low traffic)
    Cloud SQL: ~$8-15 (db-f1-micro, smallest instance)
    Networking: ~$1-3
```

**Pros:**
- Scales to zero — no cost when nobody is visiting
- Managed TLS, managed database backups
- Google Cloud free tier covers significant Cloud Run usage
- No servers to manage. No SSH. No OS patching.

**Cons:**
- Cloud SQL minimum cost (~$8/mo) even with zero traffic
- Cold start latency (2-10 seconds after scaling to zero)
- Requires GCP account and billing setup

**Best for:** Developers who want a hands-off demo that costs little when idle.

### Option 2: VPS + docker-compose

```
VPS Architecture
────────────────

  doctor.ramanshrivastava.com
         │
         ▼
  ┌──────────────────────────────────────────────┐
  │  VPS (DigitalOcean Droplet / Hetzner CX22)    │
  │  Ubuntu 24.04 LTS                              │
  │  2 vCPU, 2GB RAM, 40GB SSD                     │
  │                                                │
  │  ┌──────────────────────────────────────────┐ │
  │  │  nginx (host-level)                       │ │
  │  │  - TLS termination (certbot/Let's Encrypt)│ │
  │  │  - Reverse proxy to containers            │ │
  │  └───────────┬──────────────────────────────┘ │
  │              │                                  │
  │  ┌───────────▼──────────────────────────────┐ │
  │  │  docker-compose                           │ │
  │  │                                           │ │
  │  │  ┌──────────┐  ┌──────────┐  ┌────────┐ │ │
  │  │  │ frontend │  │ backend  │  │postgres│ │ │
  │  │  │ nginx    │  │ FastAPI  │  │  16    │ │ │
  │  │  │ :3000    │  │ :8000    │  │ :5432  │ │ │
  │  │  └──────────┘  └──────────┘  └────────┘ │ │
  │  │                                           │ │
  │  │  Network: doctor-net (bridge)             │ │
  │  │  Volumes: pgdata (persistent)             │ │
  │  └───────────────────────────────────────────┘ │
  │                                                │
  └────────────────────────────────────────────────┘

  Estimated Cost: $5-12/month
    Hetzner CX22: €4.15/mo (~$5)
    DigitalOcean Droplet: $6-12/mo
    TLS: Free (Let's Encrypt)
    Domain: Already owned
```

**Pros:**
- Cheapest option. Hetzner at ~$5/mo gets you a capable VPS.
- No cold starts — always running, always responsive.
- Full control over the environment. Docker-compose is simple and familiar.
- Everything from Document 11's VM deployment section applies directly.

**Cons:**
- **You** manage OS updates, security patches, and backups.
- If the VPS goes down, you need to notice and fix it.
- No auto-scaling (fine for a demo with low traffic).
- PostgreSQL data is on a single disk — no automatic replication.

**Best for:** Developers comfortable with Linux basics who want the cheapest option with full control.

### Option 3: GKE Autopilot

```
GKE Architecture
────────────────

  doctor.ramanshrivastava.com
         │
         ▼
  ┌────────────────────────────────────────────────────────┐
  │  GKE Autopilot Cluster                                   │
  │                                                          │
  │  ┌────────────────────────────────────────────────────┐ │
  │  │  Ingress Controller (GCE L7 LB)                     │ │
  │  │  TLS: cert-manager + Let's Encrypt                   │ │
  │  └──────────┬──────────────────┬───────────────────────┘ │
  │             │                  │                          │
  │       /*    │           /api/* │                          │
  │             ▼                  ▼                          │
  │  ┌──────────────┐   ┌──────────────┐                     │
  │  │frontend-svc  │   │backend-svc   │──► Claude API       │
  │  │ClusterIP     │   │ClusterIP     │                     │
  │  └──────┬───────┘   └──────┬───────┘                     │
  │         │                  │                              │
  │  ┌──────▼───────┐   ┌─────▼────────┐                     │
  │  │nginx pods x2 │   │uvicorn pods  │                     │
  │  │              │   │x2            │                     │
  │  └──────────────┘   └──────┬───────┘                     │
  │                            │                              │
  │                   postgres-service:5432                   │
  │                            │                              │
  │                     ┌──────▼───────┐                      │
  │                     │PostgreSQL    │                      │
  │                     │StatefulSet x1│                      │
  │                     │PVC: 20Gi    │                      │
  │                     └──────────────┘                      │
  │                                                          │
  │  Full K8s: RBAC, NetworkPolicies, pod security,          │
  │  rolling updates, health checks, auto-scaling            │
  └────────────────────────────────────────────────────────────┘

  Estimated Cost: $75-150/month
    GKE Autopilot: ~$70-120 (cluster management + pod resources)
    Persistent disk: ~$2-5
    Load balancer: ~$18
    Egress: ~$1-5
```

**Pros:**
- Demonstrates real Kubernetes skills on your portfolio.
- Everything from docs 01-11 is directly applied.
- Auto-scaling, rolling updates, RBAC, NetworkPolicies — production patterns.
- Transferable skills to any employer running K8s.

**Cons:**
- **$75-150/month** for a portfolio demo is expensive.
- Significant operational complexity for a demo project.
- Over-engineered for the traffic level (likely <100 visits/day).

**Best for:** Developers actively learning K8s who can justify the monthly cost as an educational expense.

### Option 4: PaaS (Fly.io / Railway)

```
PaaS Architecture (Fly.io example)
───────────────────────────────────

  doctor.ramanshrivastava.com
         │
         ▼
  ┌──────────────────────────────────┐
  │  Fly.io Platform                   │
  │                                    │
  │  ┌──────────────┐                 │
  │  │ doctor-app    │  ← Single Fly app (or split into 2)
  │  │ (backend)     │    Machine: shared-cpu-1x, 256MB
  │  │ FastAPI       │──► Claude API
  │  └──────┬───────┘                 │
  │         │                          │
  │  ┌──────▼───────┐                 │
  │  │ Fly Postgres  │  ← Managed PG on Fly
  │  │ (1x shared)   │    Automatic failover
  │  └──────────────┘                 │
  │                                    │
  │  Frontend: served as static files  │
  │  from backend or separate machine  │
  │                                    │
  │  TLS: automatic                    │
  │  Custom domain: CNAME setup        │
  └────────────────────────────────────┘

  Estimated Cost: $5-15/month
    Fly Machine (backend): ~$3-7
    Fly Postgres: ~$3-7
    Frontend: served from backend or free static hosting
    TLS: Free (automatic)
```

**Pros:**
- Simple deployment (Dockerfile + `fly deploy`).
- Automatic TLS, custom domain support, managed Postgres.
- Good developer experience. Less operational burden than VPS.
- Fly.io and Railway both support Docker natively.

**Cons:**
- Less control than VPS. Platform-specific configuration.
- Database options are more limited than Cloud SQL.
- Pricing can be unpredictable with usage spikes.

**Best for:** Developers who want something between VPS DIY and cloud-managed complexity.

### Decision Matrix

| Factor | Cloud Run + Cloud SQL | VPS + compose | GKE Autopilot | PaaS (Fly/Railway) |
|---|---|---|---|---|
| **Monthly cost** | $10-25 | $5-12 | $75-150 | $5-15 |
| **Cold starts** | Yes (2-10s) | No | No | Possible |
| **Operational burden** | Low | Medium | Medium | Low |
| **Learning demonstration** | Cloud-native | Linux + Docker | Full Kubernetes | Platform-specific |
| **Scales to zero** | Yes | No | No | Depends |
| **Database management** | Managed | Self-managed | Self-managed (in-cluster) | Platform-managed |
| **Best showcase for** | Cloud architecture | Full-stack dev | K8s/DevOps roles | Shipping products |

### The Honest Recommendation

For a portfolio demo, **start with a VPS or PaaS.** Here is why:

1. **Cost:** $5-12/month versus $75-150/month. The K8s cluster costs 10x more for the same result.
2. **Always-on:** No cold starts. When a recruiter clicks your demo link, it responds immediately.
3. **Simplicity:** `docker-compose up` works. You already know it from local development.
4. **Graduation path:** Start with VPS, then migrate to Cloud Run or GKE when you have a reason to (traffic growth, team collaboration, learning goals).

If you are specifically targeting DevOps/platform engineering roles and want to demonstrate K8s skills, run GKE for 1-2 months, document the setup thoroughly in a blog post or README, then tear it down and switch to a VPS. Screenshots and documentation demonstrate K8s skills just as well as a running cluster, at $0/month.

---

## 5. The Portfolio Integration Pattern

Once AI Doctor is deployed on a subdomain, you need to integrate it into your portfolio site so visitors discover it naturally.

### The Project Card

Your portfolio likely has a projects section. Add AI Doctor as a featured project card:

```
Portfolio Integration
─────────────────────

  ramanshrivastava.com
  ┌────────────────────────────────────────────────┐
  │                                                │
  │  Projects                                      │
  │  ────────                                      │
  │                                                │
  │  ┌────────────────────────────────────────┐   │
  │  │  🏥 AI Doctor Assistant                 │   │
  │  │                                         │   │
  │  │  AI-powered clinical briefing tool.     │   │
  │  │  FastAPI + React + Claude + PostgreSQL  │   │
  │  │                                         │   │
  │  │  [View Live Demo]  [View Source]        │   │
  │  │    ↓                   ↓                │   │
  │  │  doctor.raman...     github.com/...     │   │
  │  └────────────────────────────────────────┘   │
  │                                                │
  └────────────────────────────────────────────────┘
```

The "View Live Demo" link points to `https://doctor.ramanshrivastava.com`. The "View Source" link points to the GitHub repository. This is the standard pattern for developer portfolios.

### Health Monitoring: What Happens When the Demo Is Down?

Your portfolio is on Vercel — it has essentially 100% uptime. But AI Doctor is on a VPS or Cloud Run — it can go down. What does a visitor experience when they click "View Live Demo" and the app is unreachable?

**Problem:** A broken demo link is worse than no demo link. It signals carelessness.

**Solutions:**

```
Health Check Strategies
───────────────────────

Strategy 1: Backend Health Endpoint
  FastAPI exposes GET /health → { "status": "ok", "db": "connected" }
  External monitor (UptimeRobot, free tier) pings every 5 minutes.
  Alerts you via email/Slack if the app is down.

Strategy 2: Graceful Degradation in Portfolio
  Portfolio card checks demo health before showing "Live Demo" button.
  If the demo is down, show "Demo temporarily unavailable" instead of
  a broken link.

  // portfolio/components/ProjectCard.tsx
  const [demoUp, setDemoUp] = useState(true);
  useEffect(() => {
    fetch("https://doctor.ramanshrivastava.com/health")
      .then(r => { if (!r.ok) setDemoUp(false); })
      .catch(() => setDemoUp(false));
  }, []);

Strategy 3: Static Fallback
  If the live demo is down, link to a Loom video or screenshot walkthrough
  as a fallback. The visitor still sees the project in action.
```

**Recommendation:** Use Strategy 1 (health monitoring) plus Strategy 3 (video fallback). External monitoring is free and takes 2 minutes to set up. A walkthrough video ensures the project is always presentable regardless of infrastructure status.

### Cost Optimization: Scale-to-Zero vs Always-On

If you use Cloud Run or a PaaS that supports scale-to-zero, your app costs almost nothing when idle. But the tradeoff is **cold start latency** — the first request after a period of inactivity takes 2-10 seconds while the container spins up.

```
Scale-to-Zero Timeline
──────────────────────

  Recruiter clicks "View Demo" at 3:00 PM
  │
  ├── If always-on (VPS, GKE):
  │     Response in ~200ms. Normal experience.
  │
  └── If scale-to-zero (Cloud Run):
        3:00:00  Request arrives. No running instance.
        3:00:01  Cloud Run starts new instance
        3:00:03  Container starts, Python imports, uvicorn binds
        3:00:05  FastAPI ready. Request processed.
        3:00:05  Response sent. (5 second delay)
        │
        ├── Subsequent requests: ~200ms (instance is warm)
        └── After 15 min idle: instance shut down, back to cold
```

For a portfolio demo, the cold start tradeoff depends on traffic patterns:

| Scenario | Better Choice | Why |
|---|---|---|
| Applied to 50 jobs, expect steady traffic | Always-on (VPS) | Visitors arrive sporadically, each hitting cold starts |
| Low traffic, cost matters most | Scale-to-zero (Cloud Run) | Save $5-15/mo, accept occasional cold starts |
| Demo next week, must be fast | Always-on (VPS) | Cannot risk cold start during a live demo |

### Shared Design Language

A subtle but important detail: if your portfolio has a specific design language (color scheme, typography, layout patterns), the AI Doctor demo should feel related, not jarring.

This does not mean matching themes pixel-for-pixel. It means:
- Consistent typography (if your portfolio uses Inter, AI Doctor should too)
- Compatible color temperature (if portfolio is cool-toned, avoid warm orange themes)
- Similar level of polish (if portfolio is minimal, AI Doctor should not be maximalist)

This communicates that you are a developer who thinks about user experience holistically, not just within a single project.

---

## Part 2: How Managed Databases Actually Work

When you use Cloud SQL (PostgreSQL), Atlas (MongoDB), or ElastiCache (Redis), what is actually running under the hood? Is it Kubernetes? VMs? Something else entirely?

This matters because it affects how you think about database architecture, what failure modes to expect, and why managed databases cost what they cost.

---

## 6. The Two Planes

Every managed database service is built on a fundamental separation between **two planes**:

### Control Plane

The control plane handles management operations: provisioning new instances, scaling resources, running backups, performing failovers, applying patches, monitoring health, and presenting the management UI/API.

This is the code that runs when you click "Create Database" in the Cloud Console or run `gcloud sql instances create`.

### Data Plane

The data plane handles actual database operations: storing data, executing queries, managing transactions, replicating data between nodes, and serving read/write requests from your application.

This is the code that runs when your FastAPI backend executes `SELECT * FROM patients WHERE id = 42`.

```
The Two Planes
──────────────

  ┌──────────────────────────────────────────────────────────────┐
  │  CONTROL PLANE                                                │
  │  (Management Layer)                                           │
  │                                                              │
  │  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐ │
  │  │Provision │  │ Backup   │  │ Monitor   │  │ Patch /   │ │
  │  │Instances │  │ Schedule │  │ Health    │  │ Upgrade   │ │
  │  └──────────┘  └──────────┘  └───────────┘  └───────────┘ │
  │                                                              │
  │  Runs on: Kubernetes, Borg, or custom orchestration          │
  │  Characteristics: stateless, can restart freely, API-driven  │
  │                                                              │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │  DATA PLANE                                                   │
  │  (Database Engine)                                            │
  │                                                              │
  │  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐ │
  │  │ Query    │  │ Storage  │  │ Replica-  │  │ Transac-  │ │
  │  │ Execute  │  │ Engine   │  │ tion      │  │ tion Mgmt │ │
  │  └──────────┘  └──────────┘  └───────────┘  └───────────┘ │
  │                                                              │
  │  Runs on: Dedicated VMs with direct disk access              │
  │  Characteristics: stateful, I/O sensitive, needs stable IPs  │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
```

### Why This Separation Exists

The control plane and data plane have fundamentally different requirements:

| Requirement | Control Plane | Data Plane |
|---|---|---|
| **State** | Stateless (metadata in a separate store) | Heavily stateful (your data) |
| **Restart tolerance** | Can restart any time | Must not restart mid-transaction |
| **I/O sensitivity** | Low (API calls, metadata reads) | Extreme (every query hits disk) |
| **Network stability** | Can use dynamic IPs | Needs stable, low-latency connections |
| **Scale pattern** | Horizontal (more API servers) | Vertical (bigger VM) + read replicas |
| **Failure impact** | Cannot manage, but data still served | Data unavailable |

The control plane is a perfect fit for Kubernetes: stateless, horizontally scalable, restart-friendly. The data plane is a terrible fit for Kubernetes: stateful, I/O-sensitive, restart-hostile. This is why the two planes run on different infrastructure.

---

## 7. Why NOT Kubernetes for Databases

This section explains why cloud providers run database engines on VMs instead of Kubernetes pods. These are not theoretical concerns — they are engineering constraints discovered through decades of operating databases at scale.

### I/O Latency

Databases live and die by I/O performance. Every query that hits disk (which is most queries) depends on storage latency.

In Kubernetes, storage is abstracted through **PersistentVolumes (PVs)**. A PV might be backed by a cloud disk (GCE Persistent Disk, AWS EBS), but the path from the database process to the actual disk involves multiple abstraction layers:

```
I/O Path Comparison
───────────────────

VM (Direct Disk Access):
  PostgreSQL → Linux filesystem → NVMe/SSD driver → physical disk
  Latency: ~100-200μs per I/O operation

Kubernetes (PersistentVolume):
  PostgreSQL → container filesystem → PV mount → CSI driver → cloud API → physical disk
  Latency: ~500-2000μs per I/O operation (2-10x slower)

  The extra layers:
  ┌─────────────────┐
  │ Container FS     │  overlay filesystem (adds ~50μs)
  ├─────────────────┤
  │ PV CSI Driver    │  translates K8s storage requests to cloud API
  ├─────────────────┤
  │ Cloud Disk API   │  network call to attach/detach volumes
  ├─────────────────┤
  │ Network Fabric   │  if using network-attached storage (most cloud disks)
  ├─────────────────┤
  │ Physical Disk    │  actual storage hardware
  └─────────────────┘
```

For a web application reading config files, the extra latency is imperceptible. For a database executing thousands of I/O operations per second, the overhead compounds into measurable query slowdowns.

### Direct Disk Access

VMs can use **local SSDs** (NVMe drives physically attached to the host machine). These provide the lowest possible latency because there is no network hop between the VM and the disk.

Kubernetes pods cannot easily use local disks in a portable way. If a pod is rescheduled to a different node, the local disk stays on the old node. Cloud providers solve this for database VMs by pinning the VM to specific hardware and managing disk replication at a lower level than Kubernetes can.

### Memory Control

Databases are aggressive memory users. PostgreSQL's `shared_buffers` pre-allocates a large chunk of RAM for caching frequently-accessed data pages. Redis keeps its entire dataset in memory.

In Kubernetes, the **OOM killer** (Out of Memory killer) can terminate any process that exceeds its memory limit. If PostgreSQL is mid-transaction and the OOM killer kills it, the result is a crashed database that needs recovery — potentially losing the in-flight transaction and requiring WAL replay.

On a dedicated VM, the database owns all the memory. There is no OOM killer competing with other workloads because there are no other workloads on the same VM.

```
Memory Isolation
────────────────

Kubernetes Pod:
  ┌────────────────────────────┐
  │  Node: 8GB total RAM        │
  │                              │
  │  ┌──────┐ ┌──────┐ ┌─────┐│
  │  │PG pod│ │App   │ │Other││
  │  │4GB   │ │2GB   │ │2GB  ││
  │  │limit │ │limit │ │limit││
  │  └──────┘ └──────┘ └─────┘│
  │                              │
  │  If PG pod exceeds 4GB:     │
  │  OOM killer terminates it!  │
  │  (even mid-transaction)     │
  └────────────────────────────┘

Dedicated VM:
  ┌────────────────────────────┐
  │  VM: 8GB total RAM          │
  │                              │
  │  ┌────────────────────────┐│
  │  │  PostgreSQL             ││
  │  │  shared_buffers: 2GB    ││
  │  │  effective_cache: 6GB   ││
  │  │  Owns all memory.       ││
  │  │  No OOM killer.         ││
  │  └────────────────────────┘│
  └────────────────────────────┘
```

### Failover Reliability

Database failover (switching from a failed primary to a standby replica) is one of the most critical operations in database management. It must happen quickly and reliably.

Kubernetes handles pod failures by rescheduling: the scheduler finds a new node, pulls the container image, mounts the PersistentVolume, and starts the container. This process takes 30-120 seconds depending on the cluster.

Database-native replication is faster and more reliable:

| Failover Method | Typical Time | How It Works |
|---|---|---|
| **K8s rescheduling** | 30-120 seconds | Detect failure → find node → pull image → mount PV → start DB → recovery |
| **PostgreSQL streaming replication** | 5-30 seconds | Standby promotes itself → clients reconnect to new primary |
| **Cloud SQL failover** | <60 seconds | Google promotes standby → IP transparently switches |
| **RDS Multi-AZ failover** | 60-120 seconds | AWS promotes standby → DNS endpoint resolves to new primary |

Database-native failover works because the standby replica is already running, already has data loaded, and just needs to switch from read-only to read-write mode. Kubernetes rescheduling starts from scratch — no warm cache, no pre-loaded data, full recovery required.

### Stable Network Identity

Databases need stable network addresses. Clients maintain connection pools that are bound to specific IP addresses. Changing IPs means all connections must be dropped and re-established.

Kubernetes pods get new IPs every time they restart. StatefulSets mitigate this with stable DNS names, but the underlying pod IP still changes. Connection pools configured with IP addresses (common in many database drivers) break on pod restart.

Dedicated VMs keep the same IP address across reboots. Managed database services provide a stable endpoint (DNS name or static IP) that does not change even during failover.

---

## 8. Managed PostgreSQL Internals

### How Cloud SQL (Google) Works Internally

Cloud SQL is Google's managed PostgreSQL (and MySQL) service. Here is what actually runs when you create a Cloud SQL instance:

```
Cloud SQL Architecture
──────────────────────

  ┌───────────────────────────────────────────────────────────────┐
  │  CONTROL PLANE (managed by Google, runs on Borg/GKE)          │
  │                                                               │
  │  ┌────────────┐  ┌────────────┐  ┌────────────┐              │
  │  │ Instance   │  │ Backup     │  │ Monitoring │              │
  │  │ Manager    │  │ Scheduler  │  │ + Alerting │              │
  │  │            │  │            │  │            │              │
  │  │ Handles:   │  │ Handles:   │  │ Handles:   │              │
  │  │ create/del │  │ daily snap │  │ CPU/mem/   │              │
  │  │ resize     │  │ PITR logs  │  │ disk/query │              │
  │  │ failover   │  │ retention  │  │ metrics    │              │
  │  └────────────┘  └────────────┘  └────────────┘              │
  │                                                               │
  ├───────────────────────────────────────────────────────────────┤
  │                                                               │
  │  DATA PLANE (dedicated VMs, NOT in K8s)                       │
  │                                                               │
  │  Primary Zone (us-central1-a)     Standby Zone (us-central1-b)│
  │  ┌────────────────────────┐      ┌────────────────────────┐  │
  │  │  VM: n1-standard-1     │      │  VM: n1-standard-1     │  │
  │  │                        │      │                        │  │
  │  │  ┌──────────────────┐ │      │  ┌──────────────────┐ │  │
  │  │  │  PostgreSQL 16   │ │      │  │  PostgreSQL 16   │ │  │
  │  │  │  (primary)       │ │      │  │  (standby)       │ │  │
  │  │  │  shared_buffers  │ │      │  │  streaming       │ │  │
  │  │  │  WAL sender      │─┼──────┼─►│  replication     │ │  │
  │  │  └──────────────────┘ │      │  └──────────────────┘ │  │
  │  │                        │      │                        │  │
  │  │  ┌──────────────────┐ │      │  ┌──────────────────┐ │  │
  │  │  │  Persistent Disk │ │      │  │  Persistent Disk │ │  │
  │  │  │  (SSD, replicated│ │      │  │  (SSD, replicated│ │  │
  │  │  │   across zones)  │ │      │  │   across zones)  │ │  │
  │  │  └──────────────────┘ │      │  └──────────────────┘ │  │
  │  └────────────────────────┘      └────────────────────────┘  │
  │                                                               │
  │  Network:                                                     │
  │  - Private IP: 10.x.x.x (VPC peering, no public internet)   │
  │  - Public IP: optional, IP-allowlisted                        │
  │  - Cloud SQL Proxy: encrypted tunnel from app to DB           │
  │                                                               │
  └───────────────────────────────────────────────────────────────┘
```

**Key internals:**

1. **Data plane runs on dedicated VMs.** Not Kubernetes pods. Each Cloud SQL instance is a Compute Engine VM with PostgreSQL installed directly on the OS.

2. **Storage is replicated block storage.** Google's Persistent Disk replicates data across multiple physical disks in the zone. This is separate from PostgreSQL's own replication.

3. **High availability uses PostgreSQL streaming replication.** The standby VM continuously replays WAL (Write-Ahead Log) records from the primary. On failover, the standby promotes itself to primary.

4. **Control plane runs on Borg or GKE.** Google's internal management systems (originally Borg, increasingly migrated to GKE internally) handle provisioning, backups, and monitoring. This is a perfect control plane workload: stateless, API-driven, horizontally scalable.

5. **Backups are disk snapshots + WAL archiving.** Automated backups take a Persistent Disk snapshot (fast, incremental) and archive WAL segments for point-in-time recovery.

### How Amazon RDS Works Internally

```
RDS Architecture (Simplified)
─────────────────────────────

  ┌─────────────────────────────────────────────────────┐
  │  CONTROL PLANE                                       │
  │  AWS internal orchestration (not customer-visible)   │
  │  Handles: provisioning, patching, backups, failover  │
  ├─────────────────────────────────────────────────────┤
  │  DATA PLANE                                          │
  │                                                     │
  │  Availability Zone A         Availability Zone B    │
  │  ┌──────────────────┐      ┌──────────────────┐   │
  │  │  EC2 Instance     │      │  EC2 Instance     │   │
  │  │  (dedicated)      │      │  (standby)        │   │
  │  │  PostgreSQL 16    │◄────►│  PostgreSQL 16    │   │
  │  │                   │ sync │                   │   │
  │  │  EBS Volume       │ repl │  EBS Volume       │   │
  │  │  (io1/gp3)        │      │  (io1/gp3)        │   │
  │  └──────────────────┘      └──────────────────┘   │
  │                                                     │
  │  Endpoint: mydb.abc123.us-east-1.rds.amazonaws.com │
  │  (DNS resolves to current primary, switches on      │
  │   failover — clients reconnect automatically)       │
  └─────────────────────────────────────────────────────┘
```

RDS follows the same pattern as Cloud SQL: dedicated EC2 instances for the data plane, AWS-internal orchestration for the control plane. The key difference is storage: RDS uses EBS (Elastic Block Store) volumes, which are network-attached storage. Amazon Aurora takes this further by separating compute from a distributed storage layer.

### How Neon Works (Serverless PostgreSQL)

Neon is a newer approach that separates compute from storage more aggressively:

```
Neon Architecture (Simplified)
──────────────────────────────

  ┌─────────────────────────────────────────────────────┐
  │  Compute Layer (scales to zero)                      │
  │  ┌──────────────────┐                               │
  │  │  PostgreSQL       │  ← VM or container            │
  │  │  (compute only)   │    Can be suspended when idle │
  │  │  No local storage │    Starts in <1 second        │
  │  └────────┬─────────┘                               │
  │           │                                          │
  ├───────────┼──────────────────────────────────────────┤
  │           │                                          │
  │  Storage Layer (always running)                      │
  │  ┌────────▼─────────┐                               │
  │  │  Pageserver       │  ← Reads pages from object   │
  │  │                   │    storage (S3) on demand     │
  │  └────────┬─────────┘                               │
  │           │                                          │
  │  ┌────────▼─────────┐                               │
  │  │  S3 / Object      │  ← WAL and page images       │
  │  │  Storage          │    stored durably             │
  │  └──────────────────┘                               │
  └─────────────────────────────────────────────────────┘

  Key difference: compute scales to zero (like Cloud Run for databases).
  Storage is always durable in object storage.
  Cost: ~$0 when idle (no compute charges).
```

Neon is interesting for the AI Doctor portfolio demo scenario because it scales to zero like Cloud Run. You only pay for compute when queries are running. The tradeoff is cold start latency (~1 second) on the first query after idle.

### How Supabase Works

Supabase is often described as "open-source Firebase." For its database layer, Supabase runs a standard PostgreSQL instance — but the hosting infrastructure varies:

- **Supabase Cloud (hosted):** Runs PostgreSQL on AWS EC2 instances. Control plane managed by Supabase. Similar to RDS in structure but with Supabase's API layer (PostgREST, GoTrue, Realtime) running alongside.
- **Supabase on Fly.io:** Supabase recently started offering PostgreSQL instances on Fly.io's infrastructure (Firecracker microVMs).

The database itself is still PostgreSQL running on a VM. What Supabase adds is the ecosystem around it: auto-generated REST APIs, authentication, realtime subscriptions, and a dashboard.

### Connection Patterns for AI Doctor

When connecting AI Doctor's backend to a managed PostgreSQL instance, there are three patterns:

```
Connection Patterns
───────────────────

Pattern 1: Direct Private IP (Cloud SQL)
  Backend pod → Private VPC network → Cloud SQL private IP
  Config: DATABASE_URL=postgresql://user:pass@10.0.0.5:5432/doctor_db
  Pros: Lowest latency, no proxy overhead
  Cons: Requires VPC peering or Shared VPC setup

Pattern 2: Cloud SQL Proxy (Cloud SQL)
  Backend pod → Cloud SQL Proxy sidecar → encrypted tunnel → Cloud SQL
  Config: DATABASE_URL=postgresql://user:pass@localhost:5432/doctor_db
  The proxy runs as a sidecar container in the same pod.
  Pros: Automatic IAM auth, encrypted connection, no VPC setup needed
  Cons: Extra container, slightly more complexity

Pattern 3: Public IP with SSL (any provider)
  Backend pod → Internet → Cloud SQL / RDS / Neon public endpoint
  Config: DATABASE_URL=postgresql://user:pass@db.neon.tech:5432/doctor_db?sslmode=require
  Pros: Works from anywhere, simplest setup
  Cons: Public internet path, higher latency, must use SSL

AI DOCTOR EXAMPLE:
For portfolio demo on a VPS: Pattern 3 with Neon (serverless, free tier).
For GKE deployment: Pattern 2 with Cloud SQL Proxy sidecar.
For Cloud Run: Pattern 1 with Cloud SQL private IP (automatic VPC connector).
```

---

## 9. Managed MongoDB Internals

### Why MongoDB Is Relevant to AI Applications

MongoDB stores data as documents (JSON-like BSON). For AI applications, this matters because:

- **Flexible schema:** AI model outputs vary in structure. A clinical briefing might have 3 flags or 12 flags. Document databases handle this naturally without schema migrations.
- **Embedding storage:** Vector embeddings (for RAG) are arrays of floats. MongoDB Atlas has native vector search, making it a combined document store + vector database.
- **Nested data:** Patient records with nested encounters, medications, and lab results map directly to documents without join tables.

AI Doctor currently uses PostgreSQL (relational, structured). If the application evolved to store variable-structure AI outputs or needed vector search for RAG, MongoDB would become a realistic consideration.

### How MongoDB Atlas Works Internally

Atlas is MongoDB's managed cloud database service. It runs on AWS, GCP, and Azure.

```
Atlas Architecture
──────────────────

  ┌──────────────────────────────────────────────────────────────┐
  │  CONTROL PLANE (Atlas Management)                             │
  │  Runs on: Kubernetes (across all three clouds)                │
  │                                                              │
  │  ┌───────────┐  ┌───────────┐  ┌────────────┐               │
  │  │ Cluster   │  │ Backup    │  │ Monitoring │               │
  │  │ Manager   │  │ Scheduler │  │ + Alerts   │               │
  │  └───────────┘  └───────────┘  └────────────┘               │
  │                                                              │
  │  Atlas uses Kubernetes for its own control plane services.    │
  │  This is a great fit: stateless, API-driven management.      │
  │                                                              │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │  DATA PLANE (Dedicated Clusters)                              │
  │  Runs on: Dedicated VMs (EC2, Compute Engine, Azure VMs)     │
  │                                                              │
  │  Replica Set (3 nodes minimum for HA)                        │
  │                                                              │
  │  Zone A              Zone B              Zone C              │
  │  ┌────────────┐    ┌────────────┐    ┌────────────┐        │
  │  │  VM         │    │  VM         │    │  VM         │        │
  │  │  mongod     │    │  mongod     │    │  mongod     │        │
  │  │  (primary)  │◄──►│  (secondary)│◄──►│  (secondary)│        │
  │  │             │    │             │    │             │        │
  │  │  Local SSD  │    │  Local SSD  │    │  Local SSD  │        │
  │  │  or NVMe    │    │  or NVMe    │    │  or NVMe    │        │
  │  └────────────┘    └────────────┘    └────────────┘        │
  │                                                              │
  │  Replication: MongoDB's built-in replica set protocol        │
  │  Failover: Automatic primary election (typically <10 seconds)│
  └──────────────────────────────────────────────────────────────┘
```

**Key internals:**

1. **Data plane: dedicated VMs.** Just like Cloud SQL and RDS, the actual MongoDB processes (`mongod`) run on dedicated virtual machines, not Kubernetes pods.

2. **Control plane: Kubernetes.** Atlas uses Kubernetes to run its management services. The Atlas API, the web dashboard, the backup orchestrator — these are containerized services running on K8s clusters managed by MongoDB Inc.

3. **Storage: local SSDs.** For dedicated clusters, Atlas uses local NVMe/SSD storage attached to the VM. This gives the best I/O performance — exactly the reason databases avoid Kubernetes PersistentVolumes.

4. **Replication: MongoDB's native protocol.** Replica sets handle their own election, failover, and data sync. This is more reliable than Kubernetes rescheduling because the secondaries are already running and have warm data.

### Atlas Serverless: A Different Architecture

Atlas Serverless is a newer offering that uses a fundamentally different architecture:

```
Atlas Serverless Architecture
─────────────────────────────

  ┌─────────────────────────────────────────────────────────┐
  │                                                         │
  │  ┌───────────────────────────────────────────────────┐ │
  │  │  Routing Layer                                     │ │
  │  │  (receives connections, routes to correct tenant)  │ │
  │  └──────────────────────┬────────────────────────────┘ │
  │                          │                               │
  │  ┌───────────────────────▼───────────────────────────┐ │
  │  │  Compute Layer (multi-tenant, shared)              │ │
  │  │  mongod processes serving multiple customers       │ │
  │  │  Auto-scales based on workload                     │ │
  │  └──────────────────────┬────────────────────────────┘ │
  │                          │                               │
  │  ┌───────────────────────▼───────────────────────────┐ │
  │  │  Storage Layer (shared, distributed)               │ │
  │  │  Data distributed across shards                    │ │
  │  │  Automatically managed                             │ │
  │  └───────────────────────────────────────────────────┘ │
  │                                                         │
  │  Multi-tenant: your data shares infrastructure with     │
  │  other customers (isolated logically, not physically).  │
  │  Scales down to near-zero cost when idle.               │
  └─────────────────────────────────────────────────────────┘

  Dedicated Clusters: Your own VMs, full isolation, predictable performance.
  Serverless: Shared infrastructure, pay-per-operation, variable performance.
```

Atlas Serverless is interesting for the same reason Neon and Cloud Run are interesting: it scales to near-zero cost when idle. For a portfolio demo with MongoDB, Serverless would be the cost-effective choice.

---

## 10. Managed Redis Internals

### Redis Is the Interesting Exception

Redis is an **in-memory** data store. Its data lives primarily in RAM, not on disk. This changes the Kubernetes trade-off calculation:

- **I/O latency:** Less relevant. Redis operations are memory-bound, not disk-bound. The I/O overhead of Kubernetes PersistentVolumes matters less because most operations never touch disk.
- **Memory control:** More relevant than ever. Redis needs precise memory allocation, and the OOM killer is a real threat.
- **Network latency:** Very relevant. Redis operations take microseconds. Network overlay latency that is invisible for PostgreSQL (millisecond queries) becomes significant for Redis (microsecond operations).

The result: some Redis providers use Kubernetes for the data plane, while others use VMs. The choice depends on which tradeoff they prioritize.

### ElastiCache (AWS) — VMs

```
ElastiCache Architecture
────────────────────────

  ┌──────────────────────────────────────────────────────┐
  │  CONTROL PLANE (AWS-managed)                          │
  │  Provisioning, failover, patching                     │
  ├──────────────────────────────────────────────────────┤
  │  DATA PLANE (Dedicated EC2 instances)                 │
  │                                                      │
  │  ┌──────────────────┐    ┌──────────────────┐       │
  │  │  EC2 Instance     │    │  EC2 Instance     │       │
  │  │  cache.r7g.large  │    │  cache.r7g.large  │       │
  │  │                   │    │                   │       │
  │  │  redis-server     │    │  redis-server     │       │
  │  │  (primary)        │◄──►│  (replica)        │       │
  │  │                   │    │                   │       │
  │  │  RAM: 13.07 GB    │    │  RAM: 13.07 GB    │       │
  │  └──────────────────┘    └──────────────────┘       │
  │                                                      │
  │  Direct network: no overlay, no CNI, lowest latency  │
  │  Fixed IPs: stable endpoint for connection pools     │
  └──────────────────────────────────────────────────────┘
```

ElastiCache uses dedicated EC2 instances. Each Redis node runs on a VM with direct network access and dedicated RAM. This follows the same VM-for-data-plane pattern as RDS and Cloud SQL.

### Memorystore (Google Cloud) — VMs

Google's Memorystore for Redis also runs on dedicated VMs. The architecture mirrors ElastiCache: dedicated Compute Engine instances, direct network access, stable IPs. The control plane runs on Google's internal infrastructure (Borg/GKE).

### Redis Cloud (Redis Ltd.) — Kubernetes

Redis Cloud is the exception that proves the rule. Redis Ltd. (the company behind Redis) runs its managed Redis service **on Kubernetes:**

```
Redis Cloud Architecture (Kubernetes-based)
───────────────────────────────────────────

  ┌──────────────────────────────────────────────────────────────┐
  │  Kubernetes Cluster (managed by Redis Ltd.)                    │
  │                                                              │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
  │  │ Redis    │  │ Redis    │  │ Redis    │  │ Redis    │  │
  │  │ Pod A    │  │ Pod B    │  │ Pod C    │  │ Pod D    │  │
  │  │ (master) │  │ (replica)│  │ (master) │  │ (replica)│  │
  │  │          │  │          │  │          │  │          │  │
  │  │ Shard 1  │  │ Shard 1  │  │ Shard 2  │  │ Shard 2  │  │
  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
  │                                                              │
  │  Redis Enterprise operator manages:                          │
  │  - Shard placement and rebalancing                           │
  │  - Failover (Redis-native, not K8s rescheduling)             │
  │  - Memory management                                         │
  │  - Cluster topology                                          │
  │                                                              │
  │  Why K8s works here:                                         │
  │  - Redis is in-memory → disk I/O overhead less critical      │
  │  - Redis Enterprise has its own failover (not K8s restarts)  │
  │  - Operational automation via K8s operators                   │
  │  - Multi-tenant efficiency (many small Redis instances on    │
  │    shared K8s nodes)                                         │
  └──────────────────────────────────────────────────────────────┘
```

**Why Redis Cloud can use Kubernetes when others cannot:**

1. **In-memory workload.** The biggest Kubernetes penalty (storage I/O latency) barely affects Redis because most operations are memory-only.
2. **Custom failover.** Redis Enterprise does not rely on Kubernetes rescheduling for failover. It uses Redis's own replication and promotion, which is faster and more reliable.
3. **Multi-tenancy efficiency.** Redis instances are often small (128MB-2GB). Running each on a dedicated VM wastes resources. Kubernetes allows efficient bin-packing of many small Redis instances onto shared nodes.
4. **Redis Enterprise operator.** A custom Kubernetes operator manages Redis-specific concerns (shard placement, rebalancing) that generic K8s primitives cannot handle.

### Upstash — Serverless Redis

Upstash takes a different approach entirely: serverless Redis with per-request pricing. Data is persisted to disk (not purely in-memory), and the service scales to zero cost when idle.

```
Upstash Architecture (Simplified)
──────────────────────────────────

  ┌─────────────────────────────────────────┐
  │  Client request                          │
  │         │                                │
  │  ┌──────▼──────┐                        │
  │  │  Proxy Layer │  ← Routes to correct  │
  │  │  (edge)      │    region/database     │
  │  └──────┬──────┘                        │
  │         │                                │
  │  ┌──────▼──────┐                        │
  │  │  Redis Engine│  ← Modified Redis with │
  │  │  + Disk      │    durable storage     │
  │  └─────────────┘                        │
  │                                          │
  │  Pricing: per-command ($0.2 per 100K)    │
  │  Idle cost: $0                           │
  └─────────────────────────────────────────┘
```

For AI Doctor's portfolio demo, Upstash would be relevant if you needed caching (cache Claude API responses to reduce costs) or rate limiting. The serverless model means zero cost when the demo is idle.

---

## 11. The Pattern: Data Plane on VMs, Control Plane Varies

### The Universal Architecture

Across every major managed database service, one pattern emerges:

```
The Universal Pattern
─────────────────────

  ┌─────────────────────────────────────────────────────────────┐
  │                                                             │
  │  Control Plane                                              │
  │  (management, provisioning, monitoring)                     │
  │                                                             │
  │  Runs on: Whatever is best for stateless orchestration      │
  │           - Google: Borg → migrating to GKE                 │
  │           - AWS: internal orchestration systems              │
  │           - MongoDB Atlas: Kubernetes                        │
  │           - Redis Cloud: Kubernetes                          │
  │           - Neon: Kubernetes                                 │
  │                                                             │
  │  ═════════════════════════════════════════════════════════  │
  │                                                             │
  │  Data Plane                                                 │
  │  (actual database engine, query execution, storage)         │
  │                                                             │
  │  Runs on: Dedicated VMs (almost always)                     │
  │           - Cloud SQL: Compute Engine VMs                    │
  │           - RDS: EC2 instances                               │
  │           - Atlas Dedicated: EC2/CE/Azure VMs                │
  │           - ElastiCache: EC2 instances                       │
  │           - Memorystore: Compute Engine VMs                  │
  │                                                             │
  │  Exception: Redis Cloud (data plane on K8s)                 │
  │  Reason: in-memory workload, custom failover operator       │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘
```

### Summary Table

| Service | Provider | Database | Control Plane | Data Plane |
|---|---|---|---|---|
| **Cloud SQL** | Google | PostgreSQL/MySQL | Borg/GKE | Dedicated VMs (Compute Engine) |
| **RDS** | AWS | PostgreSQL/MySQL | AWS internal | Dedicated VMs (EC2) |
| **Aurora** | AWS | PostgreSQL/MySQL | AWS internal | Compute: EC2, Storage: distributed |
| **Neon** | Neon | PostgreSQL | Kubernetes | Compute: VMs/containers, Storage: S3 |
| **Supabase** | Supabase | PostgreSQL | Kubernetes | EC2 or Fly.io VMs |
| **Atlas Dedicated** | MongoDB | MongoDB | Kubernetes | Dedicated VMs |
| **Atlas Serverless** | MongoDB | MongoDB | Kubernetes | Shared multi-tenant |
| **ElastiCache** | AWS | Redis | AWS internal | Dedicated VMs (EC2) |
| **Memorystore** | Google | Redis | Borg/GKE | Dedicated VMs (Compute Engine) |
| **Redis Cloud** | Redis Ltd. | Redis | Kubernetes | **Kubernetes** (exception) |
| **Upstash** | Upstash | Redis | Custom | Custom (serverless) |

### Why Cloud Providers Built It This Way

Cloud providers did not choose VMs for databases because Kubernetes did not exist. **Kubernetes did exist** — Google released Kubernetes in 2014, and AWS/GCP have had managed Kubernetes since 2015-2017. They chose VMs because the engineering requirements of databases (I/O performance, memory control, failover reliability, stable networking) are better served by VMs.

This is not a temporary state. As of 2025, no major cloud provider has migrated their managed database data planes to Kubernetes. The constraints are fundamental, not historical.

### When Self-Hosting a Database in Kubernetes DOES Make Sense

Despite all the above, there are legitimate reasons to run a database in Kubernetes:

1. **Kubernetes operators** (CloudNativePG, Percona Operator, Zalando Postgres Operator) have matured significantly. They handle failover, backups, and scaling using database-native mechanisms, not K8s rescheduling.

2. **Development and staging environments.** The performance overhead of K8s storage is irrelevant for non-production workloads. Running PostgreSQL in K8s for dev keeps your entire stack in one cluster.

3. **Cost optimization.** If you already have a K8s cluster with spare resources, running a database pod is free. Managed databases cost $8-100+/month minimum.

4. **Air-gapped or on-premises environments.** If you cannot use cloud-managed databases, K8s operators are the next best option for automated database management.

5. **AI Doctor's learning path.** Running PostgreSQL in GKE (as docs 01-11 describe) is a valid learning exercise. You understand both the K8s deployment model AND why production databases use managed services.

```
AI DOCTOR EXAMPLE:
AI Doctor runs PostgreSQL as a StatefulSet in GKE (docs 05-06) for learning.
For a production deployment, you would migrate to Cloud SQL:
  - Replace StatefulSet + PVC with Cloud SQL instance
  - Replace postgres-service (ClusterIP) with ExternalName Service
  - Backend DATABASE_URL changes from "postgres-service:5432" to Cloud SQL Proxy
  - Everything else (backend, frontend, Ingress) stays the same

The application code does not change. Only the infrastructure configuration
changes. This is the power of Kubernetes Service abstraction.
```

---

## Part 3: Putting It Together

---

## 12. AI Doctor Deployment Plan

### Recommended Architecture for Portfolio Showcase

Combining the deployment target analysis (section 4) with managed database knowledge (sections 6-11), here is the recommended architecture for deploying AI Doctor as a portfolio demo:

```
Recommended: VPS + Neon (Serverless PostgreSQL)
───────────────────────────────────────────────

  ramanshrivastava.com                     doctor.ramanshrivastava.com
         │                                          │
         ▼                                          ▼
  ┌─────────────┐                          ┌────────────────────────────┐
  │ Vercel CDN   │                          │ VPS (Hetzner CX22)         │
  │              │                          │ Ubuntu 24.04 LTS            │
  │ Next.js      │                          │                            │
  │ Portfolio    │                          │ ┌────────────────────────┐ │
  │              │                          │ │ nginx                   │ │
  └─────────────┘                          │ │ TLS (Let's Encrypt)     │ │
                                           │ │ Reverse proxy           │ │
  DNS: CNAME → vercel                      │ └──────────┬─────────────┘ │
  TLS: Vercel auto                         │            │               │
  Cost: $0                                 │ ┌──────────▼─────────────┐ │
                                           │ │ docker-compose          │ │
                                           │ │                         │ │
                                           │ │ ┌─────────┐ ┌────────┐│ │
                                           │ │ │frontend │ │backend ││ │
                                           │ │ │nginx    │ │FastAPI ││ │
                                           │ │ │:3000    │ │:8000   ││ │
                                           │ │ └─────────┘ └───┬────┘│ │
                                           │ │                  │     │ │
                                           │ └──────────────────┼─────┘ │
                                           │                    │       │
                                           └────────────────────┼───────┘
                                                                │
                                              DATABASE_URL      │
                                              (SSL, public IP)  │
                                                                ▼
                                           ┌────────────────────────────┐
                                           │ Neon (Serverless PostgreSQL)│
                                           │                            │
                                           │ Free tier: 0.5 GB storage  │
                                           │ Auto-suspend after 5 min   │
                                           │ Branching for dev/prod     │
                                           │ ~1 second cold start       │
                                           │                            │
                                           │ Cost: $0 (free tier)       │
                                           └────────────────────────────┘

  DNS: A record → VPS IP
  TLS: certbot + Let's Encrypt
  Cost: ~$5/month (VPS only)
```

### Why This Specific Combination

| Component | Choice | Reasoning |
|---|---|---|
| **Portfolio hosting** | Vercel (keep existing) | Already working, free, no changes needed |
| **AI Doctor hosting** | Hetzner VPS (CX22, ~$5/mo) | Cheapest always-on option, no cold starts, full control |
| **Database** | Neon free tier | $0, serverless, auto-suspend, sufficient for demo traffic |
| **Domain routing** | Subdomain (`doctor.ramanshrivastava.com`) | Clean separation, one DNS record, no path prefix issues |
| **TLS** | Let's Encrypt via certbot | Free, automated renewal, standard approach |
| **Container orchestration** | docker-compose | Already used in local dev, simplest deployment |

### Cost Breakdown

| Item | Monthly Cost |
|---|---|
| Portfolio (Vercel) | $0 |
| VPS (Hetzner CX22) | ~$5 |
| Database (Neon free tier) | $0 |
| Domain (already owned) | $0 |
| TLS (Let's Encrypt) | $0 |
| **Total** | **~$5/month** |

### Migration Path

Start simple. Graduate complexity when you have a reason.

```
Migration Path
──────────────

Stage 1: Portfolio Demo (NOW)
  VPS + docker-compose + Neon
  Cost: ~$5/mo
  Skills demonstrated: Docker, full-stack, deployment

Stage 2: Cloud-Native (when learning Cloud Run)
  Cloud Run + Cloud SQL
  Cost: ~$15-25/mo
  Skills demonstrated: GCP, serverless, managed databases

Stage 3: Kubernetes (when studying for K8s roles)
  GKE Autopilot (full setup from docs 01-11)
  Cost: ~$75-150/mo
  Skills demonstrated: K8s, RBAC, NetworkPolicies, CI/CD
  (Run for 1-2 months, document everything, then downgrade)

Stage 4: Production (if AI Doctor becomes a real product)
  GKE + Cloud SQL + Cloud CDN + monitoring
  Cost: ~$100-300/mo
  Skills demonstrated: production operations, scaling, observability

Each stage builds on the previous one. The application code barely changes.
The infrastructure configuration evolves.
```

---

## 13. Summary

### Key Takeaways

1. **Subdomain is the right deployment pattern.** `doctor.ramanshrivastava.com` keeps your portfolio and demo independent. One DNS record, separate TLS, no routing complexity. This is the same pattern companies use for `api.company.com` and `docs.company.com`.

2. **Start with a VPS for a portfolio demo.** $5/month, no cold starts, docker-compose you already know. Graduate to Cloud Run or GKE when you have a concrete reason (learning goals, traffic growth, team collaboration).

3. **Managed databases run on VMs, not Kubernetes.** Cloud SQL, RDS, Atlas Dedicated, ElastiCache, and Memorystore all run their data planes on dedicated VMs. The engineering reasons are fundamental: I/O performance, memory control, failover reliability, and stable networking.

4. **The control plane / data plane split is universal.** Control planes (provisioning, backups, monitoring) are stateless and run well on Kubernetes. Data planes (query execution, storage) are stateful and run better on VMs.

5. **Redis Cloud is the exception.** In-memory workloads tolerate Kubernetes overhead better than disk-bound databases. Redis Cloud runs its data plane on K8s with a custom operator for failover.

6. **Neon and serverless databases change the cost equation.** Scale-to-zero PostgreSQL means $0 database costs for low-traffic demos. The tradeoff is ~1 second cold start on first query after idle.

### Relevant Documents in This Series

| Topic | Where to Read |
|---|---|
| Kubernetes fundamentals (Pods, Services, Deployments) | [01-KUBERNETES-FUNDAMENTALS.md](./01-KUBERNETES-FUNDAMENTALS.md) |
| How K8s manifests map to AI Doctor | [05-APP-ON-K8S.md](./05-APP-ON-K8S.md) |
| Dockerfiles, CI/CD, deployment pipeline | [06-DEPLOYMENT-PIPELINE.md](./06-DEPLOYMENT-PIPELINE.md) |
| nginx, reverse proxies, Ingress controllers | [10-NGINX-PROXIES-AND-INGRESS.md](./10-NGINX-PROXIES-AND-INGRESS.md) |
| Security layers, NetworkPolicies, RBAC | [11-SECURITY-DISCOVERY-AND-WHY-K8S.md](./11-SECURITY-DISCOVERY-AND-WHY-K8S.md) |
| VM vs K8s tradeoffs, deployment comparison | [11-SECURITY-DISCOVERY-AND-WHY-K8S.md](./11-SECURITY-DISCOVERY-AND-WHY-K8S.md) (Part 1 & 4) |
| Full series overview and glossary | [00-OVERVIEW.md](./00-OVERVIEW.md) |

---

> **This completes the Infrastructure & Kubernetes Learning Guide.** You now have the knowledge to deploy AI Doctor from local docker-compose to a live portfolio demo, and the understanding to evaluate cloud infrastructure decisions — from DNS routing to managed database internals. Return to [00-OVERVIEW.md](./00-OVERVIEW.md) for the full series index.
