# Nginx, Reverse Proxies, and Ingress Controllers

> **Document 10 of 12** in the [Infrastructure & Kubernetes Learning Guide](./00-OVERVIEW.md)
>
> **Purpose:** Clarify the roles of web servers, application servers, reverse proxies, and Ingress controllers. Explain how the classic "nginx in front of everything" pattern from VM deployments transforms when you move to Kubernetes. Show exactly what runs inside each pod and why.
>
> **Prerequisites:** Documents 01-06 (core K8s concepts, GKE, tooling, app mapping, CI/CD). You should understand Pods, Services, Deployments, Ingress resources, and how the AI Doctor Assistant is structured (FastAPI backend + React frontend + PostgreSQL).

---

## Table of Contents

1. [Web Servers vs Application Servers](#1-web-servers-vs-application-servers)
2. [What nginx Does (Deep Dive)](#2-what-nginx-does-deep-dive)
3. [Traditional VM Deployment Pattern](#3-traditional-vm-deployment-pattern)
4. [How Kubernetes Changes This Pattern](#4-how-kubernetes-changes-this-pattern)
5. [Frontend Pod: nginx Serving React](#5-frontend-pod-nginx-serving-react)
6. [Backend Pod: uvicorn vs gunicorn + uvicorn Workers](#6-backend-pod-uvicorn-vs-gunicorn--uvicorn-workers)
7. [Ingress Controllers: nginx-ingress vs Traefik](#7-ingress-controllers-nginx-ingress-vs-traefik)
8. [Other Reverse Proxies (Brief Mentions)](#8-other-reverse-proxies-brief-mentions)
9. [Where Everything Is Configured (AI Doctor Specific)](#9-where-everything-is-configured-ai-doctor-specific)
10. [Common Mistakes and Misconceptions](#10-common-mistakes-and-misconceptions)
11. [Summary](#11-summary)

---

## 1. Web Servers vs Application Servers

Before diving into nginx, Ingress controllers, or Kubernetes routing, you need a clear mental model of two fundamentally different kinds of servers. People conflate them constantly, and that confusion leads to broken architectures.

### What a Web Server Does

A **web server** handles the HTTP protocol and serves files from disk. When a browser requests `https://doctor-app.example.com/assets/main.a1b2c3.js`, a web server:

1. Parses the HTTP request (method, path, headers)
2. Maps the URL path to a file on the local filesystem
3. Reads the file from disk
4. Sends it back as an HTTP response with correct headers (Content-Type, Cache-Control, etc.)

That is the core job. A web server does not execute application logic. It does not connect to databases. It does not call external APIs. It reads files and sends them over HTTP.

**Examples of web servers:**
- **nginx** -- event-driven, high-performance, the most widely deployed web server today
- **Apache httpd** -- process/thread-based, the original dominant web server, still widely used
- **Caddy** -- modern, automatic HTTPS, simple configuration

Web servers are *extremely* good at what they do. nginx can serve tens of thousands of static file requests per second on modest hardware because it is optimized for exactly this: reading files from disk and writing bytes to network sockets.

### What an Application Server Does

An **application server** runs your code. When a browser sends `POST /api/briefings` with a JSON body, an application server:

1. Receives the HTTP request
2. Routes it to the correct handler function in your code
3. Executes your Python/Ruby/Java/Node.js logic (query database, call Claude API, build response)
4. Returns a dynamically generated HTTP response

The response is not a file on disk. It is computed at runtime. Every request potentially produces a different response.

**Examples of application servers:**
- **uvicorn** -- ASGI server for Python async frameworks (FastAPI, Starlette)
- **gunicorn** -- WSGI/ASGI server for Python, manages worker processes
- **Puma** -- multi-threaded server for Ruby (Rails)
- **Node.js** -- JavaScript runtime with built-in HTTP server
- **Tomcat / Jetty** -- Java servlet containers

### Why the Distinction Matters

The distinction matters because each type of server is optimized for a completely different workload pattern:

| Characteristic | Web Server (nginx) | Application Server (uvicorn) |
|---|---|---|
| **Primary job** | Serve files from disk | Execute application code |
| **CPU usage** | Minimal (I/O bound) | High (compute bound) |
| **Memory usage** | Low, predictable | Varies with application |
| **Concurrency model** | Event loop, thousands of connections | Workers/threads, limited by CPU |
| **Scaling bottleneck** | Disk I/O, network bandwidth | CPU, memory, external services |
| **Response time** | Sub-millisecond for cached files | Milliseconds to seconds |
| **What it serves** | HTML, CSS, JS, images, fonts | JSON, HTML templates, API responses |
| **State** | Stateless (reads files) | Stateful (DB connections, sessions) |
| **Crash impact** | Static files unavailable | Application logic unavailable |
| **Configuration** | Declarative config files | Application code + config |

```
AI DOCTOR EXAMPLE:
The AI Doctor Assistant has both types:

Web server (nginx in frontend pod):
  Serves the React build output: index.html, main.a1b2c3.js, styles.css
  No Python, no database, no Claude API calls
  Just reads files from /usr/share/nginx/html and sends them

Application server (uvicorn in backend pod):
  Runs FastAPI, handles POST /api/briefings
  Queries PostgreSQL for patient data
  Calls Claude API to generate AI briefings
  Returns dynamically computed JSON responses
```

In production, you almost always use *both* together. The web server handles what it is good at (static files, HTTP protocol, TLS) and forwards dynamic requests to the application server. This is the **reverse proxy** pattern, which we will explore next.

---

## 2. What nginx Does (Deep Dive)

nginx (pronounced "engine-x") is the most deployed web server and reverse proxy in the world. It serves roughly a third of all websites. Understanding what it does -- and what it does not do -- is essential for anyone deploying web applications.

### Brief History

nginx was created by **Igor Sysoev** in 2004 to solve the **C10K problem** -- how to handle 10,000 concurrent connections on a single server. At the time, Apache httpd used a **thread-per-connection** model: each incoming connection got its own OS thread. This worked well at hundreds of connections but collapsed at thousands because OS threads consume memory (typically 1-8MB each) and context switching between thousands of threads becomes expensive.

Sysoev designed nginx with an **event-driven architecture**. Instead of one thread per connection, nginx uses a small number of worker processes (typically one per CPU core), each running an event loop that handles thousands of connections simultaneously. The worker never blocks waiting for I/O -- it registers interest in an event (data available on socket, file read complete) and moves on to serve other connections. When the event fires, the worker processes it.

This is the same architecture pattern used by Node.js (libuv event loop) and Redis (single-threaded event loop). The insight is that most web server work is I/O-bound (waiting for disk reads, network writes, upstream responses), not CPU-bound. An event-driven model spends almost zero time waiting.

### Core Capabilities

nginx does many things, but they all fall into a few categories. Here is each one explained in detail.

#### Serving Static Files

The most basic nginx job. Given a URL path, nginx maps it to a file on disk and serves it:

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;

    location / {
        # GET /assets/main.js → serve /usr/share/nginx/html/assets/main.js
        try_files $uri $uri/ /index.html;
    }
}
```

nginx uses `sendfile()` (a Linux kernel system call) to transfer file contents directly from disk to network socket without copying data through user space. This is significantly faster than reading a file into application memory and then writing it to the socket.

#### Reverse Proxying

A **reverse proxy** sits between clients and backend servers. The client talks to the proxy, the proxy forwards the request to the appropriate backend, receives the response, and sends it back to the client. The client never communicates with the backend directly.

```nginx
server {
    listen 80;

    # Forward /api/* requests to the backend application server
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Why reverse proxy instead of letting clients connect directly?

1. **Single entry point** -- clients connect to one address, nginx routes internally
2. **SSL termination** -- nginx handles HTTPS, backends speak plain HTTP
3. **Load balancing** -- nginx distributes requests across multiple backends
4. **Security** -- backends are not directly exposed to the internet
5. **Request buffering** -- nginx absorbs slow client uploads, protecting backends

#### TLS Termination

TLS (HTTPS) encryption/decryption is CPU-intensive. Rather than making every backend handle TLS, nginx terminates TLS at the edge:

```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # All traffic from here to backend is plain HTTP
    location /api/ {
        proxy_pass http://localhost:8000;
    }
}
```

The browser connects to nginx over HTTPS (encrypted). nginx decrypts the request, forwards it to the backend over plain HTTP (unencrypted, but on localhost or a private network). This is called **TLS termination** because the TLS connection terminates at nginx.

#### Load Balancing

When you have multiple backend instances, nginx distributes requests across them:

```nginx
upstream backend_servers {
    # Round-robin (default): each request goes to the next server
    server 10.0.0.1:8000;
    server 10.0.0.2:8000;
    server 10.0.0.3:8000;
}

server {
    listen 80;
    location /api/ {
        proxy_pass http://backend_servers;
    }
}
```

Load balancing strategies:

| Strategy | Directive | How It Works | Use Case |
|---|---|---|---|
| **Round-robin** | (default) | Requests distributed sequentially | General-purpose, stateless backends |
| **Least connections** | `least_conn` | Sent to server with fewest active connections | Backends with varying response times |
| **IP hash** | `ip_hash` | Same client IP always goes to same server | Session affinity (sticky sessions) |
| **Weighted** | `weight=N` | Servers get proportional traffic | Servers with different capacities |
| **Random** | `random` | Random server selection | Large server pools |

#### Compression

nginx compresses responses before sending them to clients, reducing bandwidth:

```nginx
gzip on;
gzip_vary on;
gzip_min_length 1024;          # Don't compress tiny responses
gzip_types
    text/plain
    text/css
    text/javascript
    application/javascript
    application/json
    image/svg+xml;
```

A typical React bundle compresses from ~500KB to ~150KB with gzip, significantly reducing load times on slower connections. Brotli (`ngx_brotli` module) achieves even better compression ratios (~120KB for the same bundle) but is not included in the default nginx build.

#### Request Buffering

This is an underappreciated nginx feature. When a client uploads data slowly (mobile on 3G, for example), nginx **buffers the entire request body** before forwarding it to the backend. Without this, the backend worker is tied up waiting for slow client data, unable to serve other requests.

```
Without nginx buffering:
  Client (slow) ──slowly sends body──→ Backend (worker blocked for 30 seconds)

With nginx buffering:
  Client (slow) ──slowly sends body──→ nginx (buffers, backend free)
  nginx ──sends complete body instantly──→ Backend (worker busy for 50ms)
```

This is called **protecting the backend from slow clients**. nginx can hold thousands of slow connections in its event loop while the backend workers only deal with complete, ready-to-process requests.

#### Rate Limiting

nginx can limit request rates to prevent abuse:

```nginx
# Define rate limit zone: 10 requests per second per IP
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    location /api/ {
        # Allow burst of 20 requests, then enforce rate
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://localhost:8000;
    }
}
```

#### Caching

nginx can cache backend responses to avoid hitting the application server for repeated requests:

```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g;

server {
    location /api/patients {
        proxy_cache api_cache;
        proxy_cache_valid 200 5m;    # Cache 200 responses for 5 minutes
        proxy_cache_key "$request_uri";
        proxy_pass http://localhost:8000;
    }
}
```

#### SPA Routing Fallback

For single-page applications like the AI Doctor frontend, nginx needs to serve `index.html` for all client-side routes:

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

This directive says: try to serve the file at the requested path. If not found, try it as a directory. If that also fails, serve `/index.html`. React Router then reads the URL and renders the correct component.

Without this, refreshing or bookmarking `/patients/123` returns a 404 because no file exists at that path on disk.

### Summary of nginx Capabilities

```
┌─────────────────────────────────────────────────────────┐
│                    nginx capabilities                    │
├──────────────────────┬──────────────────────────────────┤
│ Static file serving  │ Fast I/O with sendfile()         │
│ Reverse proxying     │ Forward to upstream servers      │
│ TLS termination      │ HTTPS → HTTP                    │
│ Load balancing       │ Round-robin, least-conn, IP hash │
│ Compression          │ gzip, brotli                     │
│ Request buffering    │ Protect backends from slow       │
│                      │ clients                          │
│ Rate limiting        │ Per-IP or per-endpoint           │
│ Caching              │ Cache upstream responses         │
│ SPA routing          │ try_files fallback               │
│ Access control       │ IP allow/deny lists              │
│ Logging              │ Access logs, error logs          │
│ HTTP/2 support       │ Multiplexed connections          │
└──────────────────────┴──────────────────────────────────┘
```

---

## 3. Traditional VM Deployment Pattern

Before Kubernetes, the standard way to deploy a web application was on a single virtual machine (or a small number of them). Here is how the AI Doctor Assistant would be deployed on a traditional VM.

### The Classic Stack

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SINGLE VIRTUAL MACHINE                           │
│                    (e.g., GCE, EC2, DigitalOcean)                   │
│                                                                     │
│    ┌──────────────────────────────────────────────────────────┐     │
│    │                    nginx (port 80/443)                    │     │
│    │                                                          │     │
│    │  - TLS termination (HTTPS)                               │     │
│    │  - Serves React static files from /var/www/html          │     │
│    │  - Reverse proxies /api/* to localhost:8000              │     │
│    │  - Gzip compression                                      │     │
│    │  - Rate limiting                                         │     │
│    │  - Request buffering                                     │     │
│    │                                                          │     │
│    └───────────┬──────────────────────┬───────────────────────┘     │
│                │                      │                              │
│         static files           /api/* proxy                         │
│                │                      │                              │
│                ▼                      ▼                              │
│    ┌──────────────────┐    ┌──────────────────────────────┐        │
│    │  /var/www/html    │    │  gunicorn (port 8000)        │        │
│    │                   │    │    ├── uvicorn worker 1      │        │
│    │  index.html       │    │    ├── uvicorn worker 2      │        │
│    │  assets/          │    │    ├── uvicorn worker 3      │        │
│    │    main.js        │    │    └── uvicorn worker 4      │        │
│    │    styles.css     │    │                              │        │
│    │    images/        │    │  Running: FastAPI app         │        │
│    └──────────────────┘    └────────────┬─────────────────┘        │
│                                          │                          │
│                                          │ TCP :5432                │
│                                          ▼                          │
│                              ┌──────────────────────┐              │
│                              │  PostgreSQL           │              │
│                              │  (port 5432)          │              │
│                              │                       │              │
│                              │  Data: /var/lib/pg    │              │
│                              └──────────────────────┘              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### The Request Flow

Here is what happens when a user visits the AI Doctor app deployed on a VM:

**1. User loads the page (`GET https://doctor-app.example.com/`)**

```
Browser ──HTTPS──→ nginx (port 443)
  nginx: TLS termination (decrypt HTTPS)
  nginx: path is "/", check root directory
  nginx: serve /var/www/html/index.html
  nginx ──HTTP response──→ Browser
```

**2. Browser loads JavaScript (`GET /assets/main.a1b2c3.js`)**

```
Browser ──HTTPS──→ nginx
  nginx: TLS termination
  nginx: path matches static asset pattern
  nginx: serve /var/www/html/assets/main.a1b2c3.js
  nginx: add Cache-Control: immutable, max-age=31536000
  nginx: gzip compress response
  nginx ──compressed response──→ Browser
```

**3. App requests patient briefing (`POST /api/briefings`)**

```
Browser ──HTTPS──→ nginx
  nginx: TLS termination
  nginx: path starts with /api/, match proxy rule
  nginx: buffer request body (protect backend from slow client)
  nginx ──HTTP──→ gunicorn:8000
    gunicorn: route to available uvicorn worker
    uvicorn: FastAPI handles request
    FastAPI: query PostgreSQL for patient data
    FastAPI: call Claude API for AI briefing
    FastAPI: return JSON response
  gunicorn ──response──→ nginx
  nginx: gzip compress JSON response
  nginx ──HTTPS response──→ Browser
```

### Why nginx Sat in Front of Everything

On a VM, nginx acted as the **single entry point** because it handled multiple cross-cutting concerns that the application server should not be responsible for:

1. **TLS termination** -- gunicorn/uvicorn should not manage SSL certificates
2. **Static file serving** -- Python is slow at serving files; nginx is built for it
3. **Request buffering** -- Protects limited Python workers from slow clients
4. **Compression** -- More efficient in nginx than in Python middleware
5. **Rate limiting** -- Block abuse before it reaches the application
6. **Process supervision** -- systemd manages nginx; nginx proxies to the app

### Example nginx.conf for VM Deployment

```nginx
# /etc/nginx/sites-available/doctor-app.conf

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name doctor-app.example.com;
    return 301 https://$server_name$request_uri;
}

# Main HTTPS server
server {
    listen 443 ssl http2;
    server_name doctor-app.example.com;

    # TLS certificates (managed by certbot/Let's Encrypt)
    ssl_certificate     /etc/letsencrypt/live/doctor-app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/doctor-app.example.com/privkey.pem;

    # Modern TLS configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/javascript application/json image/svg+xml;

    # Serve React static files
    root /var/www/html/doctor-app;
    index index.html;

    # SPA routing fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets with content hashes
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Reverse proxy API requests to FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for AI briefing generation (can take 10-30 seconds)
        proxy_read_timeout 60s;
        proxy_connect_timeout 5s;

        # Request buffering
        proxy_request_buffering on;
        client_max_body_size 10m;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000;
    }

    # Rate limiting for API
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    location /api/briefings {
        limit_req zone=api burst=5 nodelay;
        proxy_pass http://127.0.0.1:8000;
    }
}
```

This single nginx config file handled *everything*: TLS, static files, reverse proxying, compression, caching, and rate limiting. On a VM, that made sense -- nginx was the only entry point.

---

## 4. How Kubernetes Changes This Pattern

When you move from a VM to Kubernetes, the "nginx does everything" pattern breaks apart. The responsibilities that were consolidated in one nginx instance get distributed across specialized components. Understanding this decomposition is the key insight of this document.

### The Decomposition

On a VM, nginx handled these responsibilities in one process:

1. TLS termination
2. Static file serving
3. Reverse proxying / routing
4. Load balancing
5. Compression
6. Rate limiting
7. Request buffering

In Kubernetes, these responsibilities are split:

```
┌────────────────────────────────────────────────────────────────────────┐
│  VM (one nginx does everything)   →   K8s (responsibilities split)   │
├──────────────────────────────────┬─────────────────────────────────────┤
│  TLS termination                 │  Ingress controller                │
│  Routing (/api/* vs /*)          │  Ingress controller                │
│  Load balancing                  │  K8s Service + Ingress controller  │
│  Rate limiting                   │  Ingress controller annotations    │
│  Request buffering               │  Ingress controller                │
│  Static file serving             │  nginx inside frontend Pod         │
│  SPA routing (try_files)         │  nginx inside frontend Pod         │
│  Compression                     │  nginx inside frontend Pod (or     │
│                                  │  Ingress controller)               │
└──────────────────────────────────┴─────────────────────────────────────┘
```

### The Kubernetes Architecture

```
                          Internet
                             │
                             ▼
              ┌──────────────────────────────┐
              │     Ingress Controller       │
              │  (nginx-ingress or GCE LB)   │
              │                              │
              │  Responsibilities:           │
              │  - TLS termination           │
              │  - Path-based routing        │
              │  - Rate limiting             │
              │  - Request buffering         │
              │  - Load balancing across     │
              │    pod replicas              │
              └──────┬───────────────┬───────┘
                     │               │
            /* paths │               │ /api/* paths
                     │               │
                     ▼               ▼
           ┌─────────────┐  ┌──────────────┐
           │  frontend   │  │   backend    │
           │  Service    │  │   Service    │
           │ ClusterIP   │  │  ClusterIP   │
           └──────┬──────┘  └──────┬───────┘
                  │                │
           ┌──────┴──────┐  ┌─────┴──────┐
           │             │  │            │
      ┌────┴───┐  ┌──────┴┐ ┌───┴────┐ ┌┴───────┐
      │ FE Pod │  │FE Pod │ │BE Pod  │ │BE Pod  │
      │        │  │       │ │        │ │        │
      │ nginx  │  │ nginx │ │uvicorn │ │uvicorn │
      │ serves │  │serves │ │runs    │ │runs    │
      │ dist/  │  │dist/  │ │FastAPI │ │FastAPI │
      └────────┘  └───────┘ └────────┘ └────────┘

   Frontend pods:             Backend pods:
   nginx (web server)         uvicorn (app server)
   Serves static files        Runs Python code
   No Python, no app code     No nginx, no static files
```

### What Each Component Does

**Ingress controller** (deployed as its own set of Pods, separate from your app):
- Terminates TLS (HTTPS connections from the internet)
- Routes requests by path: `/*` to frontend Service, `/api/*` to backend Service
- Load balances across pod replicas (works with K8s Services)
- Handles rate limiting, request buffering, and other cross-cutting concerns
- Configured via Kubernetes `Ingress` resource YAML, not an nginx.conf file

**Frontend Pod** (your app's frontend):
- Runs nginx, but *only* as a static file server
- Serves the React build output (`dist/` directory) from `/usr/share/nginx/html`
- Handles SPA routing with `try_files`
- Handles gzip compression for its own responses
- Does NOT do TLS termination (Ingress controller already did it)
- Does NOT do reverse proxying (there is nothing to proxy to)
- Does NOT do load balancing (K8s Service handles this)

**Backend Pod** (your app's backend):
- Runs uvicorn (or gunicorn with uvicorn workers)
- Runs FastAPI application code
- Does NOT run nginx at all
- Does NOT handle TLS (Ingress controller handles it)
- Does NOT serve static files (frontend pods do that)
- Talks to PostgreSQL via K8s Service DNS
- Calls Claude API over the internet

### Why the Backend Pod Does NOT Need nginx

This is the question that confuses most people transitioning from VMs to Kubernetes. On a VM, nginx sat in front of gunicorn/uvicorn. In K8s, there is no nginx in the backend pod. Why?

Because the Ingress controller already provides everything nginx used to provide on the VM:

| What nginx did on VM | What provides it in K8s |
|---|---|
| TLS termination | Ingress controller |
| Reverse proxying | Ingress controller routes directly to backend pods |
| Load balancing | K8s Service distributes across pod replicas |
| Rate limiting | Ingress controller annotations |
| Request buffering | Ingress controller |
| Compression | Can be done by Ingress controller or backend |
| Static file serving | Not needed -- frontend pods serve static files |

The backend pod only needs to do one thing: run the application. All the "nginx concerns" are handled by infrastructure that sits outside the pod.

```
AI DOCTOR EXAMPLE:
On a VM, the AI Doctor would have:
  nginx.conf → handles TLS, serves React files, proxies /api/* to uvicorn

On Kubernetes, the AI Doctor has:
  Ingress resource → routes /* to frontend Service, /api/* to backend Service
  Frontend pod → nginx serves React dist/ files (SPA routing, compression)
  Backend pod → uvicorn runs FastAPI (no nginx, no static files)

The Ingress controller replaces the "nginx in front of everything" pattern.
The frontend pod's nginx replaces only the "serve static files" part.
```

---

## 5. Frontend Pod: nginx Serving React

The frontend pod runs nginx as a lightweight static file server. This is the *only* place in the Kubernetes deployment where nginx appears in your application pods.

### The Multi-Stage Dockerfile

The frontend Dockerfile uses two stages: Node.js builds the React app, then nginx serves the output:

```dockerfile
# ─── Stage 1: Build the React application ───────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency files first (layer caching)
COPY package.json package-lock.json ./

# Clean install from lock file (reproducible builds)
RUN npm ci

# Copy source files
COPY . .

# Build production bundle
# Vite outputs to dist/ directory: index.html, assets/main.a1b2c3.js, etc.
RUN npm run build


# ─── Stage 2: Serve with nginx ──────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Remove default nginx welcome page
RUN rm -rf /usr/share/nginx/html/*

# Copy built React app from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx configuration for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# nginx listens on port 80
EXPOSE 80

# nginx:alpine image already has CMD ["nginx", "-g", "daemon off;"]
```

**Why `nginx:1.27-alpine`?** The Alpine variant is ~40MB compared to ~150MB for the Debian-based image. For a static file server that does not need additional system packages, Alpine is the right choice.

**Why remove the default page?** The default nginx image includes a "Welcome to nginx!" page. Removing it ensures only your app's files are served.

### The nginx.conf for SPA Routing

This configuration file goes into the frontend Docker image:

```nginx
# frontend/nginx.conf
# Purpose: Serve React SPA with client-side routing support

server {
    listen 80;
    server_name _;

    # Root directory containing the React build output
    root /usr/share/nginx/html;
    index index.html;

    # ── SPA routing fallback ──────────────────────────────────────
    # React Router handles client-side routing.
    # When user refreshes /patients/123, nginx must serve index.html
    # (not return 404), so React Router can handle the route.
    location / {
        try_files $uri $uri/ /index.html;
    }

    # ── Gzip compression ─────────────────────────────────────────
    # Compress text-based files before sending to client.
    # Reduces bandwidth significantly (500KB JS → ~150KB compressed).
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/javascript
        application/javascript
        application/json
        image/svg+xml
        application/xml;

    # ── Cache headers for static assets ──────────────────────────
    # Vite adds content hashes to filenames: main.a1b2c3.js
    # If content changes, filename changes → safe to cache forever.
    # "immutable" tells browser: never revalidate this URL.
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # ── Cache headers for other static files ─────────────────────
    location ~* \.(ico|png|jpg|jpeg|gif|svg|woff2|woff|ttf)$ {
        expires 30d;
        add_header Cache-Control "public";
    }

    # ── Health check endpoint ────────────────────────────────────
    # K8s liveness/readiness probes hit this endpoint.
    # Returns 200 with "ok" body — no upstream dependency.
    location /nginx-health {
        access_log off;
        return 200 'ok';
        add_header Content-Type text/plain;
    }

    # ── Security headers ─────────────────────────────────────────
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
```

### What Each Section Does

**`try_files $uri $uri/ /index.html`** -- The most critical line. Without it, refreshing a React Router page returns 404. With it, nginx always falls back to `index.html`, and React Router takes over routing in the browser.

**`gzip on`** -- Compresses responses in the frontend pod. Even though the Ingress controller could also compress, doing it here ensures compression happens regardless of Ingress configuration. The `gzip_vary` directive adds a `Vary: Accept-Encoding` header so caches store both compressed and uncompressed versions.

**`expires 1y` on `/assets/`** -- Vite generates filenames with content hashes (`main.a1b2c3.js`). When you deploy a new version, the filename changes. This means it is safe to tell browsers to cache these files forever -- they will never serve stale content because the HTML references new filenames.

**`/nginx-health`** -- A dedicated health check endpoint that Kubernetes probes hit. It does not depend on any upstream service, so it always returns 200 if nginx is running. This is used for both `livenessProbe` and `readinessProbe` in the Pod spec.

**Security headers** -- Basic browser security headers. `X-Frame-Options` prevents clickjacking, `X-Content-Type-Options` prevents MIME-type sniffing, `Referrer-Policy` controls what information is sent in the Referer header.

### How This Maps to the K8s Deployment

```yaml
# infra/k8s/base/frontend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: doctor-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
        - name: frontend
          image: us-central1-docker.pkg.dev/PROJECT/doctor-app/frontend:latest
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
          livenessProbe:
            httpGet:
              path: /nginx-health
              port: 80
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /nginx-health
              port: 80
            initialDelaySeconds: 3
            periodSeconds: 5
```

Note the resource requests: the frontend pod needs very little CPU and memory because nginx serving static files is extremely lightweight. `50m` CPU (5% of a core) and `64Mi` memory is plenty.

```
AI DOCTOR EXAMPLE:
The AI Doctor frontend pod contains:
  - nginx:1.27-alpine base image (~40MB)
  - React build output in /usr/share/nginx/html (~2MB)
  - Custom nginx.conf with SPA routing and compression

Total pod image size: ~42MB
Memory usage at runtime: ~10-30MB
What it does NOT contain: Node.js, npm, source code, node_modules
```

---

## 6. Backend Pod: uvicorn vs gunicorn + uvicorn Workers

The backend pod runs the Python application server. Unlike the frontend pod, it does not run nginx. The choice here is between running uvicorn alone or wrapping it with gunicorn for process management.

### uvicorn Alone

uvicorn is an **ASGI server** (Asynchronous Server Gateway Interface). It runs a single Python process with an async event loop that handles incoming HTTP requests and passes them to your FastAPI application.

```bash
# Single process, single worker
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**How it works:**

```
                ┌─────────────────────────────────────┐
                │         uvicorn (1 process)          │
                │                                     │
  HTTP ────────→│  async event loop                   │
  requests      │    ├── handle request 1 (await db)  │
                │    ├── handle request 2 (await api) │
                │    ├── handle request 3 (await db)  │
                │    └── ...                           │
                │                                     │
                │  FastAPI app                        │
                │    routes, middleware, dependencies  │
                └─────────────────────────────────────┘
```

uvicorn handles concurrency through Python's `asyncio` event loop. When a request awaits an I/O operation (database query, Claude API call), uvicorn suspends that request and processes others. This is efficient for I/O-bound workloads, which is exactly what the AI Doctor backend does: wait for PostgreSQL, wait for Claude API.

**When uvicorn alone is fine:**
- Development environment (hot reload with `--reload`)
- Single-pod deployments
- I/O-bound workloads with low CPU usage per request
- When Kubernetes handles scaling (more pods, not more workers per pod)

### gunicorn + uvicorn Workers

gunicorn is a **process manager** that spawns and manages multiple worker processes. When combined with uvicorn workers, each worker is a separate Python process with its own event loop:

```bash
# 4 worker processes, each running uvicorn
gunicorn src.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind 0.0.0.0:8000
```

**How it works:**

```
                ┌──────────────────────────────────────────────┐
                │          gunicorn (master process)            │
                │          Manages workers, handles signals     │
                │                                              │
                │  ┌──────────────┐  ┌──────────────┐         │
  HTTP ────────→│  │ Worker 1     │  │ Worker 2     │         │
  requests      │  │ (uvicorn)    │  │ (uvicorn)    │         │
                │  │ async loop   │  │ async loop   │         │
                │  │ FastAPI      │  │ FastAPI      │         │
                │  └──────────────┘  └──────────────┘         │
                │                                              │
                │  ┌──────────────┐  ┌──────────────┐         │
                │  │ Worker 3     │  │ Worker 4     │         │
                │  │ (uvicorn)    │  │ (uvicorn)    │         │
                │  │ async loop   │  │ async loop   │         │
                │  │ FastAPI      │  │ FastAPI      │         │
                │  └──────────────┘  └──────────────┘         │
                └──────────────────────────────────────────────┘
```

**What gunicorn adds:**
- **Process management** -- restarts crashed workers automatically
- **Graceful reload** -- send SIGHUP to reload code without downtime
- **Multiple processes** -- utilize multiple CPU cores (Python's GIL limits a single process to one core)
- **Pre-fork model** -- workers are forked before accepting requests, so startup is fast

### How Many Workers?

The classic rule of thumb is:

```
workers = (2 × CPU_CORES) + 1
```

For a pod with 1 CPU core: 3 workers. For 2 CPU cores: 5 workers.

However, in Kubernetes the calculation changes. K8s already provides horizontal scaling by running multiple pods. The question becomes: **do you want 4 pods with 1 worker each, or 2 pods with 2 workers each?**

| Approach | Pod Count | Workers per Pod | Total Workers | Tradeoff |
|---|---|---|---|---|
| **Many pods, few workers** | 4 | 1 (uvicorn only) | 4 | Better isolation, simpler, K8s-native scaling |
| **Fewer pods, more workers** | 2 | 2-4 (gunicorn) | 4-8 | More efficient memory (shared imports), fewer pods |

For most applications including the AI Doctor, **uvicorn alone with more pods is simpler and more Kubernetes-idiomatic**. Kubernetes already handles:
- Restarting crashed containers (replaces gunicorn's worker restart)
- Scaling horizontally (replaces adding more workers)
- Health checks (replaces gunicorn's worker health monitoring)

Use gunicorn + uvicorn workers when:
- Your application has CPU-intensive work that benefits from multiple processes
- You need to maximize resource efficiency per pod (large applications)
- You are running on bare metal or VMs where horizontal scaling is expensive

### Backend Dockerfile

```dockerfile
# ─── Stage 1: Build ─────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install production dependencies only
RUN uv sync --frozen --no-dev --no-editable


# ─── Stage 2: Runtime ───────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages and app from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Use the venv Python
ENV PATH="/app/.venv/bin:$PATH"

# Non-root user (security best practice)
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# ── Option A: uvicorn only (simpler, K8s-native scaling) ────────
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── Option B: gunicorn + uvicorn workers (multi-process) ────────
# CMD ["gunicorn", "src.main:app", \
#      "--worker-class", "uvicorn.workers.UvicornWorker", \
#      "--workers", "2", \
#      "--bind", "0.0.0.0:8000", \
#      "--access-logfile", "-", \
#      "--error-logfile", "-"]
```

### Health Check Endpoints

The backend exposes a `/health` endpoint that Kubernetes probes use:

```python
# backend/src/main.py
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

This endpoint should be lightweight and fast. It should NOT:
- Query the database (that makes it a dependency check, not a health check)
- Call external APIs
- Perform expensive computations

If you want to check database connectivity, use a separate `/ready` endpoint for the readiness probe:

```python
@app.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_session)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database not ready")
```

Kubernetes probe configuration in the backend Deployment:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 15
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

```
AI DOCTOR EXAMPLE:
The AI Doctor backend pod:
  - Runs uvicorn with FastAPI (Option A: single process)
  - Exposes port 8000
  - Has /health endpoint for K8s probes
  - Connects to PostgreSQL via K8s Service DNS
  - Calls Claude API for AI briefings
  - Does NOT run nginx (Ingress controller handles routing and TLS)
  - CPU request: 250m (AI briefing generation is moderately CPU-intensive)
  - Memory request: 256Mi (Python + FastAPI + dependencies)
```

---

## 7. Ingress Controllers: nginx-ingress vs Traefik

An **Ingress controller** is a Kubernetes component that implements the Ingress resource. The Ingress resource is just a YAML definition of routing rules. Without an Ingress controller running in the cluster, the Ingress resource does nothing.

### What an Ingress Controller Does

Think of the Ingress controller as the cluster-wide reverse proxy. It watches for Ingress resources via the Kubernetes API and configures itself accordingly:

```
┌─────────────────────────────────────────────────────────────┐
│                    Ingress Controller                        │
│                                                             │
│  1. Watches K8s API for Ingress resources                   │
│  2. Reads routing rules from Ingress YAML                   │
│  3. Configures internal reverse proxy (nginx, Traefik, etc.)│
│  4. Listens on port 80/443 (via LoadBalancer Service)       │
│  5. Routes incoming traffic to backend Services/Pods        │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Ingress resource says:                               │  │
│  │    - host: doctor-app.example.com                     │  │
│  │    - path: /       → frontend-service:80              │  │
│  │    - path: /api/   → backend-service:8000             │  │
│  │    - tls: use certificate from secret "tls-cert"      │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Controller translates this into actual proxy config        │
│  and starts routing traffic.                                │
└─────────────────────────────────────────────────────────────┘
```

Here is a sample Ingress resource for the AI Doctor app:

```yaml
# infra/k8s/base/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: doctor-ingress
  namespace: doctor-app
  annotations:
    # These annotations depend on which Ingress controller you use
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
spec:
  ingressClassName: nginx    # or "gce" for GKE default
  tls:
    - hosts:
        - doctor-app.example.com
      secretName: tls-secret
  rules:
    - host: doctor-app.example.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: backend-service
                port:
                  number: 8000
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-service
                port:
                  number: 80
```

### nginx-ingress Controller

The **nginx Ingress controller** (maintained by the Kubernetes community, CNCF project) is the most widely deployed Ingress controller. It runs nginx inside its own pods and dynamically generates nginx configuration based on Ingress resources.

**How it works internally:**
1. A Deployment runs nginx-ingress-controller pods
2. Controller watches for Ingress resource changes via K8s API
3. When Ingress changes, controller generates new nginx.conf
4. Controller reloads nginx with the new configuration
5. Traffic flows: Internet → LoadBalancer → nginx-ingress pods → your app pods

**Installation:**

```bash
# Using Helm
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace
```

**Key characteristics:**
- Configuration via Ingress annotations (`nginx.ingress.kubernetes.io/...`)
- Battle-tested nginx engine under the hood
- Static configuration model (rebuilds config on changes)
- Extensive documentation and community support
- Supports custom nginx snippets for advanced use cases

### Traefik

**Traefik** (pronounced "traffic") is a modern reverse proxy and Ingress controller designed for cloud-native environments. Unlike nginx-ingress, Traefik was built from the ground up for dynamic service discovery.

**How it works:**
1. Traefik pods run as a Deployment (or DaemonSet)
2. Traefik auto-discovers services via K8s API (no config rebuild needed)
3. Routes are updated in real-time as Services and Ingress resources change
4. Built-in dashboard shows routing configuration visually
5. Automatic TLS certificate management with Let's Encrypt

**Installation:**

```bash
# Using Helm
helm repo add traefik https://traefik.github.io/charts
helm install traefik traefik/traefik \
  --namespace traefik \
  --create-namespace
```

**Key characteristics:**
- Dynamic configuration (no reload needed)
- Built-in web dashboard for monitoring routes
- Automatic Let's Encrypt TLS certificates
- Middleware system for per-route features (rate limiting, auth, etc.)
- Supports both Ingress resources and its own CRDs (IngressRoute)

### GKE Default: GCE Ingress Controller

GKE comes with its own Ingress implementation backed by **Google Cloud Load Balancer (GCLB)**. When you create an Ingress resource with `ingressClassName: gce`, GKE provisions an actual Google Cloud HTTP(S) Load Balancer -- a globally distributed, highly available load balancer running on Google's infrastructure.

```
Internet → Google Cloud Load Balancer (global, managed)
              ├── /* → frontend Service → frontend Pods
              └── /api/* → backend Service → backend Pods
```

**Advantages of GCE Ingress:**
- No controller pods to manage (it is a cloud-native load balancer)
- Global load balancing (multi-region support)
- Integrated with Google Cloud Armor (WAF, DDoS protection)
- Managed TLS certificates (Google-managed certs, no Let's Encrypt needed)
- Native integration with GKE (no additional installation)

**Disadvantages:**
- Slower to provision (takes 3-5 minutes vs seconds for nginx-ingress)
- Less flexible annotation support than nginx-ingress
- Costs money (standard GCP load balancer pricing)
- Harder to test locally (no equivalent in minikube)

### Comparison Table

| Feature | nginx-ingress | Traefik | GCE Ingress (GKE) |
|---|---|---|---|
| **Maintainer** | Kubernetes/CNCF | Traefik Labs | Google |
| **Engine** | nginx | Custom Go proxy | Google Cloud LB |
| **Config style** | Annotations + ConfigMap | CRDs + annotations | Annotations |
| **Config updates** | Rebuild + reload | Dynamic, real-time | Cloud API calls |
| **TLS management** | Manual or cert-manager | Built-in Let's Encrypt | Google-managed certs |
| **Dashboard** | No built-in dashboard | Built-in web dashboard | GCP Console |
| **Rate limiting** | Annotations | Middleware CRDs | Cloud Armor rules |
| **WebSocket support** | Yes (annotation) | Yes (native) | Yes |
| **gRPC support** | Yes | Yes | Yes |
| **Performance** | Excellent (nginx core) | Very good | Excellent (global infra) |
| **Learning curve** | Moderate (nginx knowledge helps) | Low-moderate | Low (managed service) |
| **Local dev testing** | Easy (minikube addon) | Easy (Helm install) | Not available locally |
| **Community size** | Very large (most popular) | Large | GCP ecosystem |
| **Custom logic** | nginx snippets | Middleware plugins | Limited |
| **Cost** | Free (runs in your pods) | Free (runs in your pods) | GCP LB pricing |
| **Multi-cluster** | Manual setup | Supported | Traffic Director |
| **Health checks** | Configurable | Auto-detected | GCP health checks |
| **Canary deployments** | Annotation-based | Weighted routing | Not built-in |
| **Installation** | Helm chart | Helm chart | Pre-installed on GKE |
| **Maturity** | Very mature | Mature | Very mature |

### Which One for AI Doctor?

**Recommendation: Start with GKE's GCE Ingress controller.**

For the AI Doctor Assistant, the simplest path is:

1. **Development/testing**: Use nginx-ingress on minikube (available as an addon: `minikube addons enable ingress`)
2. **Production on GKE**: Use the default GCE Ingress controller (no installation needed, Google-managed TLS certificates)
3. **If you outgrow GCE Ingress**: Switch to nginx-ingress or Traefik when you need features like canary deployments, custom rate limiting rules, or WebSocket-specific configuration

The GCE Ingress controller is the right starting point because:
- Zero installation (already part of GKE)
- Managed TLS certificates (no cert-manager to set up)
- Google Cloud Armor integration (DDoS protection, WAF)
- You only need basic path-based routing (`/*` and `/api/*`)

```
AI DOCTOR EXAMPLE:
The AI Doctor Assistant uses basic path-based routing:
  - /* → frontend Service (nginx serving React files)
  - /api/* → backend Service (uvicorn running FastAPI)

This is well within the capabilities of any Ingress controller.
GCE Ingress is the simplest choice for GKE deployment.

For local testing with minikube:
  minikube addons enable ingress
  # This installs nginx-ingress controller inside minikube
  kubectl apply -f infra/k8s/base/ingress.yaml
  # Change ingressClassName to "nginx" for minikube testing
```

---

## 8. Other Reverse Proxies (Brief Mentions)

nginx-ingress and Traefik are the most common Ingress controllers, but the reverse proxy landscape is broader. Here is a brief overview of other notable options.

### Caddy

**Caddy** is a modern web server written in Go, best known for **automatic HTTPS**. When you configure a domain in Caddy, it automatically obtains and renews Let's Encrypt certificates with zero configuration.

```
# Caddyfile — entire reverse proxy config
doctor-app.example.com {
    reverse_proxy /api/* localhost:8000
    file_server {
        root /var/www/html
    }
}
```

That is the entire configuration. No ssl_certificate directives, no certificate paths, no renewal cron jobs. Caddy handles it all.

**When to use Caddy:** Small projects, side projects, situations where you want minimal configuration. Not commonly used as a Kubernetes Ingress controller, but excellent for VM deployments.

### HAProxy

**HAProxy** (High Availability Proxy) is a high-performance TCP/HTTP load balancer used by large-scale systems. It powers load balancing for GitHub, Stack Overflow, Reddit, and many other high-traffic sites.

**Key strengths:**
- Extremely high performance (millions of connections)
- Advanced load balancing algorithms
- TCP-level proxying (not just HTTP)
- Detailed metrics and monitoring
- Battle-tested at massive scale

**When to use HAProxy:** When performance is the primary concern. When you need TCP-level (Layer 4) load balancing. When running large-scale infrastructure. There is an HAProxy Ingress controller for Kubernetes, but it is less popular than nginx-ingress or Traefik.

### Envoy

**Envoy** is a modern Layer 4/Layer 7 proxy designed for cloud-native architectures. Created at Lyft, it is the data plane proxy used in service meshes like **Istio** and **AWS App Mesh**.

**Key strengths:**
- Hot restart (reload config without dropping connections)
- Advanced observability (distributed tracing, metrics)
- gRPC-native (first-class support)
- xDS API (dynamic configuration via API, not files)
- Extensible via WebAssembly filters

**When to use Envoy:** When you need a service mesh. When you need advanced observability (distributed tracing across microservices). When gRPC is a primary protocol. The **Contour** Ingress controller uses Envoy as its data plane.

### Apache httpd

**Apache httpd** is the original dominant web server, first released in 1995. It uses a **process/thread-per-connection** model (with various MPMs: prefork, worker, event).

**Current status:** Still widely used (~30% of web servers), but nginx has overtaken it for new deployments. Apache's strength is its module ecosystem (mod_rewrite, mod_security, mod_php) and its familiarity to long-time administrators.

**When to use Apache:** Legacy environments, PHP applications (mod_php), when you need specific Apache modules. Not recommended for new Kubernetes deployments.

### Comparison Table

| Proxy | Architecture | Primary Use Case | HTTPS Management | K8s Ingress? | Performance |
|---|---|---|---|---|---|
| **nginx** | Event-driven | Web server + reverse proxy | Manual or cert-manager | Yes (most popular) | Excellent |
| **Traefik** | Go, dynamic | Cloud-native reverse proxy | Auto (Let's Encrypt) | Yes (popular) | Very good |
| **Caddy** | Go, modular | Simple web server | Auto (Let's Encrypt) | Limited | Good |
| **HAProxy** | Event-driven C | High-perf load balancer | Manual | Yes (less common) | Exceptional |
| **Envoy** | C++, xDS | Service mesh data plane | Via control plane | Yes (Contour) | Excellent |
| **Apache** | Process/thread | Legacy web server | Manual | No (not practical) | Good |

For the AI Doctor Assistant, the relevant choices are nginx (inside frontend pods for static files) and either GCE Ingress, nginx-ingress, or Traefik (as the cluster Ingress controller). The other proxies solve problems that the AI Doctor does not currently have.

---

## 9. Where Everything Is Configured (AI Doctor Specific)

One of the most confusing aspects of the nginx/proxy/Ingress landscape is knowing *where* each concern is configured. Here is a definitive mapping for the AI Doctor Assistant.

### Configuration Map

| Concern | Config File Location | What It Controls |
|---|---|---|
| **Python server startup** | `backend/Dockerfile` CMD line | How uvicorn (or gunicorn) starts: host, port, workers |
| **SPA routing** | `frontend/nginx.conf` | `try_files` fallback so React Router works on refresh |
| **Gzip compression** | `frontend/nginx.conf` | Compress static assets before sending to browser |
| **Static asset caching** | `frontend/nginx.conf` | `Cache-Control` and `Expires` headers on JS/CSS/images |
| **Frontend image build** | `frontend/Dockerfile` | Multi-stage: `npm build` → copy `dist/` into `nginx:alpine` |
| **Backend image build** | `backend/Dockerfile` | Multi-stage: `uv sync` → copy `.venv` and `src/` into `python:slim` |
| **Pod resources** | `infra/k8s/base/*-deployment.yaml` | CPU/memory requests/limits, replica count |
| **Health probes** | `infra/k8s/base/*-deployment.yaml` | Liveness/readiness probe paths and timing |
| **Path-based routing** | `infra/k8s/base/ingress.yaml` | `/api/*` → backend Service, `/*` → frontend Service |
| **TLS certificates** | Ingress controller config or annotation | HTTPS termination, certificate source |
| **Rate limiting** | Ingress annotations or middleware | Request rate limits per IP or endpoint |
| **Domain name** | `infra/k8s/base/ingress.yaml` | `host:` field in Ingress spec |
| **Environment variables** | `infra/k8s/base/configmap.yaml` | Non-secret config (AI model, debug flag) |
| **Secrets** | `infra/k8s/base/secrets.yaml` | API keys, database password (base64 encoded) |
| **Service discovery** | `infra/k8s/base/*-service.yaml` | ClusterIP Services for inter-pod communication |
| **Database connection** | Backend ConfigMap or Secret | DATABASE_URL pointing to `postgres-service.doctor-app.svc` |

### Visual: Which Config Controls What

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Request Lifecycle in K8s                              │
│                                                                         │
│  Browser ──HTTPS──→ Who handles TLS?                                    │
│                     └─→ Ingress controller (ingress.yaml annotations)   │
│                                                                         │
│  ──HTTP──→ Which pod gets this request?                                 │
│            └─→ Ingress resource (ingress.yaml path rules)               │
│                                                                         │
│  ──→ Frontend pod: What does nginx serve?                               │
│       └─→ nginx.conf (try_files, gzip, cache headers)                   │
│       └─→ Dockerfile (what files are in /usr/share/nginx/html)          │
│                                                                         │
│  ──→ Backend pod: How does uvicorn run?                                 │
│       └─→ Dockerfile CMD (uvicorn command, host, port)                  │
│       └─→ K8s Deployment (resources, probes, replicas)                  │
│       └─→ ConfigMap/Secret (environment variables)                      │
│                                                                         │
│  ──→ Backend pod: How does it connect to PostgreSQL?                    │
│       └─→ ConfigMap/Secret (DATABASE_URL)                               │
│       └─→ postgres Service (provides stable DNS name)                   │
│                                                                         │
│  ──→ Backend pod: How does it call Claude API?                          │
│       └─→ Secret (ANTHROPIC_API_KEY)                                    │
│       └─→ ConfigMap (AI_MODEL setting)                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Quick Debugging Guide

When something is broken, this table tells you where to look:

| Symptom | Likely Config Issue | Check This File |
|---|---|---|
| 404 on page refresh | Missing `try_files` | `frontend/nginx.conf` |
| API requests return 502 | Backend pod not ready or wrong port | `ingress.yaml`, `backend-deployment.yaml` |
| Static files not loading | Wrong `root` path or missing files | `frontend/Dockerfile`, `frontend/nginx.conf` |
| HTTPS not working | TLS not configured in Ingress | `ingress.yaml` TLS section |
| Slow API responses | No read timeout set | Ingress annotations (`proxy-read-timeout`) |
| Large file upload fails | Body size limit too low | Ingress annotations (`proxy-body-size`) |
| Backend can't reach DB | Wrong DATABASE_URL | ConfigMap/Secret, postgres Service |
| Pod keeps restarting | Health probe failing | Deployment probes, check endpoint exists |
| 503 Service Unavailable | No ready pods | Deployment replicas, readiness probe |

---

## 10. Common Mistakes and Misconceptions

### Mistake 1: "I need nginx in every pod"

**Wrong:** Adding an nginx sidecar to your backend pod for reverse proxying.

**Right:** Backend pods run only the application server (uvicorn). The Ingress controller handles reverse proxying at the cluster level.

The only pod that needs nginx is the frontend pod, because it is serving static files. The backend pod does not serve files -- it runs Python code. Putting nginx in front of uvicorn inside a pod adds complexity and resource overhead for zero benefit, because the Ingress controller is already doing that job.

```
WRONG:
┌─────────────────────────┐
│  Backend Pod             │
│  ┌────────┐  ┌────────┐ │
│  │ nginx  │→│uvicorn │ │    ← Unnecessary. Ingress already proxies.
│  └────────┘  └────────┘ │
└─────────────────────────┘

RIGHT:
┌─────────────────────────┐
│  Backend Pod             │
│  ┌────────────────────┐ │
│  │     uvicorn        │ │    ← All you need. Ingress handles the rest.
│  │     (FastAPI)      │ │
│  └────────────────────┘ │
└─────────────────────────┘
```

### Mistake 2: "Traefik replaces nginx entirely"

**Confusion:** Thinking that because Traefik is an Ingress controller, you do not need nginx anywhere in your cluster.

**Reality:** Traefik replaces **nginx-ingress** (the Ingress controller). It does NOT replace **nginx-the-file-server** in your frontend pods. These are two completely different uses of nginx:

| Role | What it is | Replaced by Traefik? |
|---|---|---|
| **nginx-ingress controller** | Cluster-wide reverse proxy and router | Yes, Traefik replaces this |
| **nginx in frontend pod** | Static file server for React build | No, Traefik does not serve your files |

Even if you use Traefik as your Ingress controller, your frontend pods still run nginx (or another file server) to serve the React build output.

### Mistake 3: "uvicorn can't handle production traffic"

**Misconception:** uvicorn is "just for development" and you must use gunicorn in production.

**Reality:** uvicorn is a production-grade ASGI server. It handles async I/O efficiently and performs well under load. The reason people recommend gunicorn is for **process management** (restarting crashed workers, utilizing multiple CPU cores). But in Kubernetes:

- **Kubernetes restarts crashed pods** (replaces gunicorn's worker restart)
- **HPA scales pod count** (replaces adding more workers)
- **Liveness probes detect unhealthy processes** (replaces gunicorn's health monitoring)

uvicorn alone in a K8s pod is a perfectly valid production setup. Many companies run uvicorn-only FastAPI deployments in production.

### Mistake 4: "I need to configure TLS in my application"

**Wrong:** Adding `ssl_keyfile` and `ssl_certfile` to your uvicorn startup command.

**Right:** Let the Ingress controller handle TLS. Your application should only speak plain HTTP.

```bash
# WRONG: TLS in the application
uvicorn src.main:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile /etc/certs/key.pem \
  --ssl-certfile /etc/certs/cert.pem

# RIGHT: Plain HTTP, Ingress handles TLS
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

TLS termination happens at the Ingress controller. Traffic between the Ingress controller and your pods flows over the cluster's internal network, which is already isolated. Adding TLS inside pods creates certificate management complexity for no security gain in most deployments.

### Mistake 5: Confusing nginx-the-file-server with nginx-ingress-the-controller

This is the most common confusion. There are two completely different things both called "nginx":

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  "nginx" in this codebase can mean TWO different things:             │
│                                                                      │
│  1. nginx inside FRONTEND POD                                        │
│     └── What: Static file server                                     │
│     └── Runs: Inside your app's frontend Deployment                  │
│     └── Config: frontend/nginx.conf (you write this)                 │
│     └── Image: nginx:1.27-alpine                                     │
│     └── Serves: React build files (index.html, main.js, styles.css) │
│     └── Scope: One pod, one concern (serve files)                    │
│                                                                      │
│  2. nginx-ingress CONTROLLER                                         │
│     └── What: Cluster-wide reverse proxy + load balancer             │
│     └── Runs: In its own namespace (ingress-nginx)                   │
│     └── Config: Ingress resource YAML + annotations                  │
│     └── Image: registry.k8s.io/ingress-nginx/controller              │
│     └── Routes: Internet traffic to correct Services                  │
│     └── Scope: All Ingress resources in the cluster                   │
│                                                                      │
│  They share the name "nginx" but serve COMPLETELY different roles.   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

When someone says "does the app use nginx?", the answer is:
- **Yes**, the frontend pod uses nginx to serve static files
- **Maybe**, the cluster may use nginx-ingress as its Ingress controller (or it may use Traefik, or GCE Ingress)
- These are independent decisions

### Mistake 6: "My backend needs to serve the frontend files too"

**Wrong:** Configuring FastAPI to serve the React build with `StaticFiles` middleware in production.

**Right:** Frontend and backend are separate pods. The frontend pod serves its own files via nginx. The backend pod only handles API requests.

```python
# WRONG: Serving frontend from FastAPI in production
app.mount("/", StaticFiles(directory="frontend/dist", html=True))

# RIGHT: FastAPI handles only API routes
# Frontend files are served by nginx in a separate pod
```

In development, Vite's dev server proxies API requests to the backend. In production, the Ingress controller routes requests: `/*` to the frontend pod (nginx), `/api/*` to the backend pod (uvicorn). The backend never sees or serves frontend files.

### Mistake 7: "I should use the same nginx.conf on VM and in K8s"

The VM nginx.conf handles TLS, static files, reverse proxying, compression, rate limiting, and caching -- all in one file. In K8s, these responsibilities are split:

| VM nginx.conf section | K8s equivalent |
|---|---|
| `ssl_certificate` | Ingress TLS configuration |
| `location /api/ { proxy_pass }` | Ingress path rules |
| `location / { try_files }` | Frontend pod nginx.conf |
| `gzip on` | Frontend pod nginx.conf |
| `limit_req` | Ingress annotations |
| `proxy_cache` | Ingress annotations or CDN |

The frontend pod's nginx.conf should be *much simpler* than a VM nginx.conf because it only handles static file serving and SPA routing. Everything else is handled by the Ingress controller or Kubernetes primitives.

---

## 11. Summary

The deployment architecture shifts fundamentally when you move from a single VM to Kubernetes. The key pattern to internalize is:

**VM pattern:** One nginx process handles everything (TLS, routing, static files, proxying, compression, rate limiting).

**Kubernetes pattern:** Responsibilities are distributed to specialized components, each running in its own pods.

### What Runs Where

```
┌──────────────────────────────────────────────────────────────────────┐
│  Component              │  What It Runs          │  What It Does     │
├─────────────────────────┼────────────────────────┼───────────────────┤
│  Ingress controller     │  nginx-ingress,        │  TLS termination, │
│  (cluster infra)        │  Traefik, or GCE LB    │  path routing,    │
│                         │                        │  rate limiting,   │
│                         │                        │  load balancing   │
├─────────────────────────┼────────────────────────┼───────────────────┤
│  Frontend Pod           │  nginx:alpine          │  Serve React      │
│  (your app)             │                        │  static files,    │
│                         │                        │  SPA routing,     │
│                         │                        │  gzip compression │
├─────────────────────────┼────────────────────────┼───────────────────┤
│  Backend Pod            │  uvicorn (or gunicorn  │  Run FastAPI,     │
│  (your app)             │  + uvicorn workers)    │  handle API       │
│                         │                        │  requests, call   │
│                         │                        │  Claude API,      │
│                         │                        │  query PostgreSQL │
├─────────────────────────┼────────────────────────┼───────────────────┤
│  PostgreSQL Pod         │  PostgreSQL 16         │  Store patient    │
│  (StatefulSet)          │                        │  data             │
└─────────────────────────┴────────────────────────┴───────────────────┘
```

### The Three Key Rules

1. **Frontend pod = nginx (web server).** It serves static files. No application logic.
2. **Backend pod = uvicorn (application server).** It runs Python code. No nginx needed.
3. **Ingress controller = cluster-wide reverse proxy.** It handles TLS, routing, and cross-cutting concerns that nginx handled on a VM.

### The Full Request Flow in K8s

```
Browser (HTTPS)
    │
    ▼
Ingress Controller
    │ TLS termination (HTTPS → HTTP)
    │ Path-based routing
    │
    ├── GET / ──────────→ frontend Service ──→ frontend Pod (nginx)
    │                                            └── serve index.html
    │
    ├── GET /assets/* ──→ frontend Service ──→ frontend Pod (nginx)
    │                                            └── serve JS/CSS files
    │                                               (gzip, cache headers)
    │
    ├── POST /api/* ────→ backend Service ──→ backend Pod (uvicorn)
    │                                           └── FastAPI handles request
    │                                              └── query PostgreSQL
    │                                              └── call Claude API
    │                                              └── return JSON
    │
    └── GET /health ────→ backend Service ──→ backend Pod (uvicorn)
                                                └── return {"status": "healthy"}
```

```
AI DOCTOR EXAMPLE:
The AI Doctor Assistant's production architecture on GKE:

1. GCE Ingress controller (Google-managed load balancer):
   - Terminates TLS with Google-managed certificate
   - Routes /* to frontend Service, /api/* to backend Service
   - No pods to manage (it is a cloud-native load balancer)

2. Frontend pods (2 replicas):
   - nginx:1.27-alpine serving React build output
   - ~42MB image, ~20MB runtime memory
   - try_files for SPA routing, gzip compression

3. Backend pods (2 replicas):
   - python:3.12-slim running uvicorn with FastAPI
   - ~150MB image, ~256MB runtime memory
   - Connects to PostgreSQL, calls Claude API

4. PostgreSQL StatefulSet (1 replica):
   - Persistent storage via PVC
   - Accessed by backend pods via K8s Service DNS

No nginx anywhere near the backend pods. The Ingress controller
handles everything that nginx used to handle on a VM. The frontend
pods use nginx solely as a static file server.
```

---

> **Next Steps**: Proceed to [11-SECURITY-DISCOVERY-AND-WHY-K8S.md](./11-SECURITY-DISCOVERY-AND-WHY-K8S.md) to understand when Kubernetes is (and is not) the right tool, how to secure a cluster across 5 defense layers, and how pods discover each other via built-in DNS. Or return to `08-KNOWLEDGE-CHECK.md` to test your understanding of nginx, Ingress controllers, and application server patterns.
