# AI Doctor Assistant Mapped to Kubernetes

This document maps the AI Doctor Assistant application from its local development architecture to a production-ready GKE deployment. We'll cover the architecture transformation, all required Kubernetes manifests, environment configuration strategy, and necessary code changes.

## 1. Current Local Architecture

```
┌──────────┐    HTTP     ┌──────────────┐    asyncpg    ┌──────────────┐
│ Browser  │───────────→│ Vite Dev     │               │              │
│          │  :5173     │ Server       │               │  PostgreSQL  │
└──────────┘            └──────────────┘               │  (Docker     │
                              │ proxy /api              │   Compose)   │
                              ▼                         │  :5432       │
                        ┌──────────────┐               │              │
                        │ Uvicorn      │───────────────→│              │
                        │ FastAPI      │               └──────────────┘
                        │ :8000        │
                        │              │────→ Claude API (external)
                        └──────────────┘
```

**Local Development Flow:**
- Frontend: Vite dev server on :5173 with HMR
- Backend: Uvicorn on :8000, proxied via Vite
- Database: PostgreSQL 16 via Docker Compose
- AI: Direct HTTPS calls to Claude API (api.anthropic.com)

**Configuration:**
- `backend/src/config.py`: Settings class with `anthropic_api_key`, `ai_model` (default "claude-opus-4-6"), `database_url`, `debug`
- CORS hardcoded to `["http://localhost:5173"]` in `backend/src/main.py:38`
- Environment variables loaded from `.env` file

## 2. Target GKE Architecture

```
                    Internet
                       │
                ┌──────┴──────┐
                │   Ingress   │
                │  (GCP LB)   │
                └──┬───────┬──┘
          /*       │       │    /api/*
                   ▼       ▼
        ┌──────────────┐ ┌──────────────┐
        │  FE Service  │ │  BE Service  │
        │ ClusterIP:80 │ │ClusterIP:8000│
        └──────┬───────┘ └──────┬───────┘
               │                │
        ┌──────┴──────┐  ┌─────┴──────┐
        │  FE Pod 1   │  │  BE Pod 1  │
        │  (nginx)    │  │  (uvicorn) │────→ Claude API
        ├─────────────┤  ├────────────┤
        │  FE Pod 2   │  │  BE Pod 2  │
        │  (nginx)    │  │  (uvicorn) │────→ Claude API
        └─────────────┘  └─────┬──────┘
                                │
                         ┌──────┴──────┐
                         │  PG Service │
                         │ClusterIP:5432│
                         └──────┬──────┘
                                │
                         ┌──────┴──────┐
                         │PG StatefulSet│
                         │  (1 replica) │
                         │  + PVC 10Gi  │
                         └─────────────┘
```

**Production Flow:**
- Single external IP (GCP Load Balancer via Ingress)
- Path-based routing: `/*` → frontend, `/api/*` + `/health` → backend
- Frontend: 2 replicas of nginx serving React build
- Backend: 2 replicas of uvicorn with health probes
- Database: StatefulSet with persistent storage
- Secrets: API keys and DB credentials in K8s Secrets
- Config: Environment-specific values in ConfigMaps

## 3. Kubernetes Manifests

### 3.1 Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: doctor-app
  labels:
    app: ai-doctor-assistant
    environment: production
```

All resources will be deployed in this namespace to provide logical isolation.

### 3.2 Frontend Deployment and Service

**frontend-deployment.yaml:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: doctor-app
  labels:
    app: ai-doctor-assistant
    component: frontend
spec:
  # Run 2 replicas for high availability
  replicas: 2
  selector:
    matchLabels:
      app: ai-doctor-assistant
      component: frontend
  template:
    metadata:
      labels:
        app: ai-doctor-assistant
        component: frontend
    spec:
      containers:
      - name: nginx
        # Built from frontend/Dockerfile (multi-stage: npm build → nginx)
        image: gcr.io/PROJECT_ID/doctor-assistant-frontend:latest
        ports:
        - containerPort: 80
          name: http
          protocol: TCP

        # Resource requests ensure QoS and proper scheduling
        resources:
          requests:
            cpu: 250m      # 0.25 CPU cores
            memory: 256Mi  # 256 megabytes
          limits:
            cpu: 500m
            memory: 512Mi

        # Liveness probe: Is nginx alive?
        # Failure → container restart
        livenessProbe:
          httpGet:
            path: /
            port: 80
            scheme: HTTP
          initialDelaySeconds: 10  # Wait 10s after container start
          periodSeconds: 10        # Check every 10s
          timeoutSeconds: 3
          successThreshold: 1
          failureThreshold: 3      # Restart after 3 consecutive failures

        # Readiness probe: Is nginx ready to serve traffic?
        # Failure → remove from Service endpoints
        readinessProbe:
          httpGet:
            path: /
            port: 80
            scheme: HTTP
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 2
          successThreshold: 1
          failureThreshold: 2

        # Security context: run as non-root
        securityContext:
          runAsNonRoot: true
          runAsUser: 101  # nginx user
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop:
            - ALL

        # nginx needs writable /var/cache and /var/run
        volumeMounts:
        - name: cache
          mountPath: /var/cache/nginx
        - name: run
          mountPath: /var/run

      volumes:
      - name: cache
        emptyDir: {}
      - name: run
        emptyDir: {}

      # Topology spread ensures pods are distributed across nodes
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            app: ai-doctor-assistant
            component: frontend
```

**frontend-service.yaml:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: doctor-app
  labels:
    app: ai-doctor-assistant
    component: frontend
spec:
  # ClusterIP: internal-only, exposed via Ingress
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 80
    protocol: TCP
    name: http
  selector:
    app: ai-doctor-assistant
    component: frontend
  # Session affinity not needed for stateless frontend
  sessionAffinity: None
```

### 3.3 Backend Deployment and Service

**backend-deployment.yaml:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: doctor-app
  labels:
    app: ai-doctor-assistant
    component: backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ai-doctor-assistant
      component: backend
  template:
    metadata:
      labels:
        app: ai-doctor-assistant
        component: backend
    spec:
      containers:
      - name: fastapi
        # Built from backend/Dockerfile (Python 3.12 + uv + uvicorn)
        image: gcr.io/PROJECT_ID/doctor-assistant-backend:latest
        ports:
        - containerPort: 8000
          name: http
          protocol: TCP

        # Environment variables from ConfigMap and Secret
        env:
        # From ConfigMap (non-sensitive config)
        - name: AI_MODEL
          valueFrom:
            configMapKeyRef:
              name: backend-config
              key: AI_MODEL
        - name: DEBUG
          valueFrom:
            configMapKeyRef:
              name: backend-config
              key: DEBUG
        - name: CORS_ORIGINS
          valueFrom:
            configMapKeyRef:
              name: backend-config
              key: CORS_ORIGINS

        # From Secret (sensitive credentials)
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: backend-secrets
              key: ANTHROPIC_API_KEY
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: backend-secrets
              key: DATABASE_URL

        # Resource requests for backend (more than frontend)
        resources:
          requests:
            cpu: 500m      # 0.5 CPU cores
            memory: 512Mi
          limits:
            cpu: 1000m     # 1 CPU core
            memory: 1Gi

        # Startup probe: Give FastAPI 60s to start (loads AI model config)
        # Disables liveness/readiness until startup succeeds
        startupProbe:
          httpGet:
            path: /health
            port: 8000
            scheme: HTTP
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          successThreshold: 1
          failureThreshold: 12  # 12 * 5s = 60s max startup time

        # Liveness probe: Is the process alive?
        # Failure → container restart
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
            scheme: HTTP
          initialDelaySeconds: 0   # Startup probe handles initial delay
          periodSeconds: 10
          timeoutSeconds: 3
          successThreshold: 1
          failureThreshold: 3

        # Readiness probe: Can it serve traffic?
        # Failure → remove from Service endpoints
        # This should check database connectivity
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
            scheme: HTTP
          initialDelaySeconds: 0
          periodSeconds: 5
          timeoutSeconds: 2
          successThreshold: 1
          failureThreshold: 2

        # Security context
        securityContext:
          runAsNonRoot: true
          runAsUser: 1000
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: false  # Python needs write access for __pycache__
          capabilities:
            drop:
            - ALL

      # Topology spread across nodes
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            app: ai-doctor-assistant
            component: backend
```

**backend-service.yaml:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: doctor-app
  labels:
    app: ai-doctor-assistant
    component: backend
spec:
  type: ClusterIP
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
    name: http
  selector:
    app: ai-doctor-assistant
    component: backend
  sessionAffinity: None
```

### 3.4 PostgreSQL StatefulSet and Service

**postgres-statefulset.yaml:**

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: doctor-app
  labels:
    app: ai-doctor-assistant
    component: database
spec:
  # StatefulSet ensures stable network identity and persistent storage
  serviceName: postgres  # Headless service name
  replicas: 1            # Single replica (no HA in this setup)
  selector:
    matchLabels:
      app: ai-doctor-assistant
      component: database
  template:
    metadata:
      labels:
        app: ai-doctor-assistant
        component: database
    spec:
      containers:
      - name: postgres
        image: postgres:16
        ports:
        - containerPort: 5432
          name: postgres
          protocol: TCP

        # PostgreSQL configuration from Secret
        env:
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: backend-secrets
              key: POSTGRES_USER
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: backend-secrets
              key: POSTGRES_PASSWORD
        - name: POSTGRES_DB
          value: "doctor_assistant"
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata  # Subdirectory required

        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 1000m
            memory: 2Gi

        # Liveness probe: Is PostgreSQL accepting connections?
        livenessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - $(POSTGRES_USER)
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          successThreshold: 1
          failureThreshold: 3

        # Readiness probe: Can it handle queries?
        readinessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - $(POSTGRES_USER)
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          successThreshold: 1
          failureThreshold: 2

        # Mount persistent volume
        volumeMounts:
        - name: postgres-data
          mountPath: /var/lib/postgresql/data

        securityContext:
          runAsNonRoot: true
          runAsUser: 999  # postgres user
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: false  # PostgreSQL needs write access

  # VolumeClaimTemplate: each pod gets its own PVC
  volumeClaimTemplates:
  - metadata:
      name: postgres-data
      labels:
        app: ai-doctor-assistant
        component: database
    spec:
      accessModes:
      - ReadWriteOnce  # Single pod can mount
      resources:
        requests:
          storage: 10Gi
      # storageClassName: standard-rwo  # GKE default (uncomment to specify)
```

**postgres-service.yaml:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: doctor-app
  labels:
    app: ai-doctor-assistant
    component: database
spec:
  # Headless service: clusterIP: None
  # Provides stable DNS for StatefulSet pods
  # DNS: postgres-0.postgres.doctor-app.svc.cluster.local
  clusterIP: None
  ports:
  - port: 5432
    targetPort: 5432
    protocol: TCP
    name: postgres
  selector:
    app: ai-doctor-assistant
    component: database
  # publishNotReadyAddresses: true ensures DNS records for non-ready pods
  publishNotReadyAddresses: true
```

### 3.5 ConfigMap

**configmap.yaml:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: backend-config
  namespace: doctor-app
  labels:
    app: ai-doctor-assistant
    component: backend
data:
  # AI model configuration
  AI_MODEL: "claude-opus-4-6"

  # Debug mode (false in production)
  DEBUG: "false"

  # CORS origins (domain-specific, no trailing slash)
  # Multiple origins: comma-separated
  CORS_ORIGINS: "https://doctor-app.example.com"

  # Optional: Database connection pool settings
  DB_POOL_SIZE: "10"
  DB_MAX_OVERFLOW: "20"
```

### 3.6 Secret

**secret.yaml:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: backend-secrets
  namespace: doctor-app
  labels:
    app: ai-doctor-assistant
    component: backend
type: Opaque
data:
  # IMPORTANT: All values must be base64-encoded
  # Example encoding: echo -n "value" | base64

  # Anthropic API key (from Claude console)
  # Example: sk-ant-api03-... (base64-encoded)
  ANTHROPIC_API_KEY: c2stYW50LWFwaTAzLWV4YW1wbGU=

  # PostgreSQL credentials
  POSTGRES_USER: ZG9jdG9y          # "doctor"
  POSTGRES_PASSWORD: c2VjdXJlcGFzcw==  # "securepass"

  # Database URL for asyncpg
  # Format: postgresql+asyncpg://USER:PASS@HOST:PORT/DB
  # HOST: postgres-0.postgres.doctor-app.svc.cluster.local (StatefulSet DNS)
  DATABASE_URL: cG9zdGdyZXNxbCthc3luY3BnOi8vZG9jdG9yOnNlY3VyZXBhc3NAcG9zdGdyZXMtMC5wb3N0Z3Jlcy5kb2N0b3ItYXBwLnN2Yy5jbHVzdGVyLmxvY2FsOjU0MzIvZG9jdG9yX2Fzc2lzdGFudA==
```

**Creating base64-encoded values:**

```bash
# Encode Anthropic API key
echo -n "sk-ant-api03-YOUR_KEY_HERE" | base64

# Encode database URL
echo -n "postgresql+asyncpg://doctor:securepass@postgres-0.postgres.doctor-app.svc.cluster.local:5432/doctor_assistant" | base64

# Encode PostgreSQL credentials
echo -n "doctor" | base64
echo -n "securepass" | base64
```

**IMPORTANT:** Never commit actual secrets to Git. Use placeholder values in the template and populate real values via CI/CD or `kubectl create secret`.

### 3.7 Ingress

**ingress.yaml:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: doctor-app
  namespace: doctor-app
  labels:
    app: ai-doctor-assistant
  annotations:
    # GKE ingress class (creates GCP HTTPS Load Balancer)
    kubernetes.io/ingress.class: "gce"

    # Enable HTTPS redirect
    kubernetes.io/ingress.allow-http: "false"

    # Google-managed SSL certificate (requires domain ownership verification)
    networking.gke.io/managed-certificates: "doctor-app-cert"

    # Backend timeout (60s for AI requests)
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "60"
spec:
  rules:
  - host: doctor-app.example.com
    http:
      paths:
      # Backend paths (API + health check)
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: backend
            port:
              number: 8000
      - path: /health
        pathType: Exact
        backend:
          service:
            name: backend
            port:
              number: 8000

      # Frontend paths (all other routes)
      # IMPORTANT: This must come AFTER backend paths (order matters)
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend
            port:
              number: 80

  # TLS configuration
  tls:
  - hosts:
    - doctor-app.example.com
    # secretName is auto-populated by managed-certificates
```

**Managed SSL Certificate (GKE):**

```yaml
apiVersion: networking.gke.io/v1
kind: ManagedCertificate
metadata:
  name: doctor-app-cert
  namespace: doctor-app
spec:
  domains:
  - doctor-app.example.com
```

## 4. Environment Variable Strategy

| Variable | Dev (local) | Staging (GKE) | Production (GKE) | Source |
|----------|-------------|---------------|-------------------|--------|
| AI_MODEL | claude-opus-4-6 | claude-opus-4-6 | claude-opus-4-6 | ConfigMap |
| DEBUG | true | false | false | ConfigMap |
| CORS_ORIGINS | http://localhost:5173 | https://staging.doctor-app.com | https://doctor-app.com | ConfigMap |
| DATABASE_URL | postgresql+asyncpg://user:pass@localhost:5432/doctor_assistant | postgresql+asyncpg://doctor:pass@postgres-0.postgres.doctor-app.svc.cluster.local:5432/doctor_assistant | postgresql://doctor:pass@10.X.X.X:5432/doctor_assistant (Cloud SQL) | Secret |
| ANTHROPIC_API_KEY | (from .env file) | (K8s Secret from CI/CD) | (Secret from GCP Secret Manager + Workload Identity) | Secret |

**Environment-Specific Overrides with Kustomize:**

```yaml
# infra/k8s/overlays/staging/kustomization.yaml
bases:
- ../../base

namespace: doctor-app-staging

configMapGenerator:
- name: backend-config
  behavior: merge
  literals:
  - CORS_ORIGINS=https://staging.doctor-app.com
  - DEBUG=false

images:
- name: gcr.io/PROJECT_ID/doctor-assistant-backend
  newTag: staging-abc123
- name: gcr.io/PROJECT_ID/doctor-assistant-frontend
  newTag: staging-abc123
```

## 5. Code Changes Required

### 5.1 Backend Configuration (backend/src/config.py)

Add `cors_origins` field to the Settings class:

```python
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    anthropic_api_key: str
    ai_model: str = "claude-opus-4-6"
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/doctor_assistant"
    debug: bool = False

    # NEW: Configurable CORS origins (comma-separated)
    cors_origins: str = "http://localhost:5173"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

### 5.2 Backend CORS Middleware (backend/src/main.py)

Replace hardcoded CORS origins with configurable value:

```python
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings

app = FastAPI(
    title="AI Doctor Assistant",
    version="2.0.0",
)

# BEFORE (line 38):
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:5173"],
#     ...
# )

# AFTER:
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),  # Split comma-separated string
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 5.3 Health Check Endpoint Enhancement

Enhance `/health` to verify database connectivity for readiness probes:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_session

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_session)):
    """
    Health check endpoint with database connectivity verification.

    Liveness probe: returns 200 if FastAPI is running
    Readiness probe: returns 200 if database is reachable
    """
    try:
        # Simple query to verify database connection
        await db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "ai_model": settings.ai_model,
        }
    except Exception as e:
        # Database unreachable → readiness probe fails → no traffic
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
            }
        )
```

## 6. Repository Restructuring

```
ai-doctor-assistant/
├── backend/
│   ├── Dockerfile                    # NEW: Multi-stage Python build
│   ├── .dockerignore                 # NEW: Exclude .env, __pycache__, tests
│   ├── src/
│   │   ├── main.py                   # UPDATED: Configurable CORS
│   │   ├── config.py                 # UPDATED: Add cors_origins field
│   │   └── ...
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── Dockerfile                    # NEW: Multi-stage npm build → nginx
│   ├── .dockerignore                 # NEW: Exclude node_modules, .env
│   ├── nginx.conf                    # NEW: SPA routing, gzip, security headers
│   ├── src/
│   ├── public/
│   └── package.json
├── infra/                            # NEW: All infrastructure code
│   └── k8s/
│       ├── base/                     # Shared manifests
│       │   ├── kustomization.yaml
│       │   ├── namespace.yaml
│       │   ├── backend-deployment.yaml
│       │   ├── backend-service.yaml
│       │   ├── frontend-deployment.yaml
│       │   ├── frontend-service.yaml
│       │   ├── postgres-statefulset.yaml
│       │   ├── postgres-service.yaml
│       │   ├── configmap.yaml
│       │   ├── secret.yaml          # Template with placeholders
│       │   └── ingress.yaml
│       └── overlays/
│           ├── dev/
│           │   ├── kustomization.yaml
│           │   └── patches/
│           │       ├── backend-replicas.yaml  # 1 replica
│           │       └── ingress-host.yaml      # dev.doctor-app.com
│           └── staging/
│               ├── kustomization.yaml
│               └── patches/
│                   ├── backend-replicas.yaml  # 2 replicas
│                   └── ingress-host.yaml      # staging.doctor-app.com
├── .github/
│   └── workflows/
│       ├── ci.yaml                   # NEW: Build + test + push images
│       └── cd.yaml                   # NEW: Deploy to GKE via Kustomize
├── docker-compose.yml                # UPDATED: Add backend + frontend services
├── docs/
│   └── infra-arch/
│       └── 05-APP-ON-K8S.md         # This file
└── CLAUDE.md
```

### Dockerfile Examples

**backend/Dockerfile:**

```dockerfile
# Multi-stage build: builder → runtime

FROM python:3.12-slim AS builder

# Install uv (fast Python package installer)
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies to /app/.venv
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Add .venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**frontend/Dockerfile:**

```dockerfile
# Multi-stage build: npm build → nginx serve

FROM node:20-slim AS builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci --prefer-offline --no-audit

# Copy source code
COPY . .

# Build production bundle
RUN npm run build

# Runtime stage
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy build output
COPY --from=builder /app/dist /usr/share/nginx/html

# Non-root user (nginx user = 101)
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx

USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

**frontend/nginx.conf:**

```nginx
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    keepalive_timeout 65;
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    server {
        listen 80;
        server_name _;
        root /usr/share/nginx/html;
        index index.html;

        # Security headers
        add_header X-Frame-Options "DENY" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;

        # SPA routing: all routes serve index.html
        location / {
            try_files $uri $uri/ /index.html;
        }

        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

## 7. Health Probes Explained

Kubernetes provides three types of health probes to monitor container health:

### 7.1 Liveness Probe

**Purpose:** "Is the process alive?"

**Behavior:** If the liveness probe fails, Kubernetes **restarts the container**. This is the nuclear option.

**Use Case:** Detect deadlocks, infinite loops, or corrupted state that requires a full restart.

**Example:** HTTP GET /health returns 200

**YAML for Backend:**

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
    scheme: HTTP
  initialDelaySeconds: 0   # Startup probe handles initial delay
  periodSeconds: 10        # Check every 10 seconds
  timeoutSeconds: 3        # Fail if no response in 3s
  successThreshold: 1      # 1 success = healthy
  failureThreshold: 3      # 3 consecutive failures = restart
```

**Interpretation:** After startup completes, check `/health` every 10 seconds. If it fails 3 times in a row (30 seconds), restart the container.

### 7.2 Readiness Probe

**Purpose:** "Can it serve traffic?"

**Behavior:** If the readiness probe fails, Kubernetes **removes the pod from Service endpoints**. No traffic is routed to it, but the container keeps running.

**Use Case:** Database connection lost, external dependency unavailable, temporary overload. The pod can recover without a restart.

**Example:** HTTP GET /health returns 200 AND database is reachable

**YAML for Backend:**

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 8000
    scheme: HTTP
  initialDelaySeconds: 0
  periodSeconds: 5         # Check every 5 seconds (more frequent than liveness)
  timeoutSeconds: 2
  successThreshold: 1
  failureThreshold: 2      # 2 failures = remove from endpoints
```

**Interpretation:** Check `/health` every 5 seconds. If it fails twice in a row (10 seconds), stop sending traffic but don't restart. Once it succeeds again, resume traffic.

### 7.3 Startup Probe

**Purpose:** "Has it finished starting?"

**Behavior:** Disables liveness and readiness probes until the startup probe succeeds. Gives slow-starting containers time to initialize.

**Use Case:** Applications that take 30+ seconds to start (loading large models, warming caches).

**YAML for Backend:**

```yaml
startupProbe:
  httpGet:
    path: /health
    port: 8000
    scheme: HTTP
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  successThreshold: 1
  failureThreshold: 12     # 12 * 5s = 60s max startup time
```

**Interpretation:** Wait 10 seconds after container start, then check every 5 seconds. Allow up to 60 seconds (12 failures) for the application to start. Once it succeeds, enable liveness/readiness probes.

### 7.4 Probe Interaction Timeline

```
Container Start
    │
    ├─ t=0s:  Container created
    ├─ t=10s: Startup probe begins (initialDelaySeconds: 10)
    ├─ t=15s: Startup probe check 1 (success)
    │         → Liveness and readiness probes now enabled
    │
    ├─ t=15s: Readiness probe check 1 (success) → added to Service endpoints
    ├─ t=20s: Readiness probe check 2 (success) → continues receiving traffic
    │
    ├─ t=25s: Liveness probe check 1 (success)
    ├─ t=35s: Liveness probe check 2 (success)
    │
    ├─ t=100s: Database connection lost
    ├─ t=100s: Readiness probe fails (DB unreachable)
    ├─ t=105s: Readiness probe fails again → removed from endpoints
    │          (No traffic, but container still running)
    │
    ├─ t=110s: Liveness probe still succeeds (FastAPI process alive)
    ├─ t=115s: Database reconnects
    ├─ t=115s: Readiness probe succeeds → added back to endpoints
    │
    └─ Traffic resumes (no restart needed)
```

### 7.5 Best Practices

1. **Startup probe for slow starts:** Use when your app takes >10s to initialize
2. **Readiness for dependencies:** Check database, Redis, external APIs
3. **Liveness for process health:** Only check if the process is responsive
4. **Different failure thresholds:** Readiness should fail faster (2x) than liveness (3x)
5. **Avoid expensive checks:** Probes run frequently; keep them fast (<100ms)

## 8. Deployment Commands

### 8.1 Deploy to GKE

```bash
# 1. Build and push images (CI/CD does this)
cd backend
docker build -t gcr.io/PROJECT_ID/doctor-assistant-backend:v1.0.0 .
docker push gcr.io/PROJECT_ID/doctor-assistant-backend:v1.0.0

cd ../frontend
docker build -t gcr.io/PROJECT_ID/doctor-assistant-frontend:v1.0.0 .
docker push gcr.io/PROJECT_ID/doctor-assistant-frontend:v1.0.0

# 2. Create namespace
kubectl apply -f infra/k8s/base/namespace.yaml

# 3. Create secrets (populate with real values first)
kubectl apply -f infra/k8s/base/secret.yaml

# 4. Apply all manifests via Kustomize
kubectl apply -k infra/k8s/overlays/staging/

# 5. Verify deployments
kubectl get pods -n doctor-app
kubectl get services -n doctor-app
kubectl get ingress -n doctor-app

# 6. Check logs
kubectl logs -n doctor-app -l component=backend --tail=50
kubectl logs -n doctor-app -l component=frontend --tail=50
```

### 8.2 Update Deployment (Rolling Update)

```bash
# Update image tag in Kustomize overlay
cd infra/k8s/overlays/staging
kustomize edit set image gcr.io/PROJECT_ID/doctor-assistant-backend:v1.1.0

# Apply
kubectl apply -k .

# Watch rollout
kubectl rollout status deployment/backend -n doctor-app
```

### 8.3 Troubleshooting

```bash
# Describe pod (shows events and probe failures)
kubectl describe pod <pod-name> -n doctor-app

# Exec into container
kubectl exec -it <pod-name> -n doctor-app -- /bin/bash

# Check probe status
kubectl get pod <pod-name> -n doctor-app -o jsonpath='{.status.conditions}'

# View Secret values (debugging only)
kubectl get secret backend-secrets -n doctor-app -o jsonpath='{.data.DATABASE_URL}' | base64 -d
```

## 9. Next Steps

This document provides the foundation for deploying the AI Doctor Assistant to GKE. In the following documents, we'll cover:

- **06-DOCKER-IMAGES.md:** Building optimized multi-stage Dockerfiles
- **07-CI-CD.md:** GitHub Actions workflows for automated deployment
- **08-OBSERVABILITY.md:** Logging, metrics, and tracing in Kubernetes
- **09-SCALING-PROD.md:** Autoscaling, Cloud SQL, Secret Manager, and production hardening

**Key Takeaways:**

1. **StatefulSet for PostgreSQL:** Provides stable DNS and persistent storage
2. **ConfigMap vs Secret:** Non-sensitive config in ConfigMap, credentials in Secret
3. **Health probes:** Startup → Liveness → Readiness, each with a specific purpose
4. **Path-based Ingress:** Single load balancer routes to frontend and backend
5. **Environment parity:** Same manifests for dev/staging/prod with Kustomize overlays
