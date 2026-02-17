# Deployment Pipeline — CI/CD, Dockerfiles, and Image Registry

This document covers the complete deployment pipeline for the AI Doctor Assistant: Docker image creation, artifact registry setup, and CI/CD workflows using GitHub Actions.

## 1. Pipeline Overview

The deployment pipeline automates the journey from code commit to running containers in GKE:

```
Developer                  GitHub                    GCP
─────────────────────────────────────────────────────────────
git push ──→ GitHub Actions ──→ Build Docker Images
                                       │
                            ┌──────────┴──────────┐
                            ▼                     ▼
                     Backend Image          Frontend Image
                            │                     │
                            └──────────┬──────────┘
                                       ▼
                              Push to Artifact Registry
                                       │
                                       ▼
                              kubectl apply -k overlays/staging/
                                       │
                                       ▼
                              GKE Autopilot Cluster
                              (rolling update)
```

Key stages:

1. **Trigger:** Developer pushes code to GitHub
2. **Build:** GitHub Actions builds Docker images
3. **Push:** Images pushed to GCP Artifact Registry
4. **Deploy:** Kubernetes manifests updated and applied
5. **Rollout:** GKE performs rolling update (zero downtime)

## 2. Backend Dockerfile (Multi-Stage Build)

The backend uses a multi-stage build to create a minimal production image:

```dockerfile
# Stage 1: Build stage — install dependencies with uv
# We use python:3.12-slim (not full python:3.12) to reduce image size
# The slim variant includes only essential packages (~150MB vs ~1GB)
FROM python:3.12-slim AS builder

# Install uv (fast Python package installer)
# Copy from official uv image rather than curl install for reproducibility
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (Docker layer caching)
# If these files don't change, Docker reuses the cached layer
# This means we don't reinstall dependencies on every code change
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev deps in production)
# --frozen: don't update lock file, fail if lock is out of sync (reproducible builds)
# --no-dev: skip pytest, ruff, and other development dependencies
# --no-editable: install packages normally, not in editable mode
RUN uv sync --frozen --no-dev --no-editable

# Copy application source
# This layer changes frequently, so it goes last
COPY src/ ./src/

# Stage 2: Runtime stage — minimal image
# Start fresh from base image to exclude build tools and intermediate artifacts
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages and app from builder
# The .venv directory contains all installed Python packages
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Use the venv's Python
# This ensures our app uses the isolated virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Non-root user for security
# Running as root violates security best practices and is blocked by some K8s policies
# UID/GID will be automatically assigned
RUN useradd --create-home appuser
USER appuser

# Expose port for documentation (K8s ignores this, uses Service port)
EXPOSE 8000

# Health check for standalone Docker (K8s uses its own probes)
# This is useful for docker-compose or local testing
# Interval: check every 30 seconds
# Timeout: fail if check takes longer than 3 seconds
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run with uvicorn
# --host 0.0.0.0: listen on all interfaces (required in containers)
# --port 8000: must match EXPOSE and K8s containerPort
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Why Multi-Stage Build?

Multi-stage builds dramatically reduce final image size:

- **Single-stage build:** ~800MB (includes uv, build tools, source packages)
- **Multi-stage build:** ~150MB (only runtime dependencies and app code)

Benefits:
- Faster image pulls across the cluster
- Reduced attack surface (no build tools in production)
- Lower registry storage costs
- Better security scanning (fewer packages to audit)

### Layer Caching Strategy

Docker builds layers sequentially and caches unchanged layers. Our Dockerfile order:

1. Base image (rarely changes)
2. Dependency files (changes on package updates)
3. Install dependencies (reused if files unchanged)
4. Application source (changes frequently)

If you modify `src/services/briefing_service.py`, Docker reuses the dependency installation layer (saving 1-2 minutes per build).

## 3. Frontend Dockerfile (Multi-Stage Build)

The frontend uses a two-stage build: Node for building, nginx for serving:

```dockerfile
# Stage 1: Build — npm install + build
# Use alpine variant for smaller image (~150MB vs ~1GB for full node:20)
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first for layer caching
# npm ci (clean install) uses package-lock.json for reproducible installs
COPY package.json package-lock.json ./

# npm ci vs npm install:
# - ci: removes node_modules first, installs exactly from lock file
# - install: may update lock file, not reproducible
RUN npm ci

# Copy source files
# This layer invalidates frequently, so it goes after dependencies
COPY . .

# Build production bundle
# Vite outputs static files to dist/ directory
# Result: HTML, JS, CSS, images — all static assets
RUN npm run build

# Stage 2: Serve — nginx serving static files
# nginx:alpine is tiny (~40MB) and purpose-built for serving static files
FROM nginx:alpine AS runtime

# Copy built assets from builder stage
# /usr/share/nginx/html is nginx's default web root
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx configuration
# See next section for configuration details
COPY nginx.conf /etc/nginx/conf.d/default.conf

# nginx listens on port 80 by default
EXPOSE 80

# No CMD needed — nginx:alpine image has default CMD to start nginx
```

### Why nginx for Frontend?

Node is designed for dynamic server-side JavaScript, not static file serving. After Vite builds the frontend:

- **Output:** Static HTML, JS, CSS files
- **Need:** Fast HTTP server for these files
- **nginx:** Lightweight (40MB), battle-tested, optimized for static files

Alternatives like `serve` (Node-based) work but add unnecessary overhead (Node runtime ~200MB).

## 4. nginx Configuration for SPA Routing

React Router handles client-side routing. When a user visits `/patients/123`, nginx must serve `index.html` (not return 404):

```nginx
server {
    # Listen on port 80 (standard HTTP)
    listen 80;

    # Root directory containing built React app
    root /usr/share/nginx/html;

    # Default file to serve
    index index.html;

    # SPA fallback — all routes serve index.html
    # This is critical for client-side routing
    # try_files: try to serve the file, then directory, then fallback
    # Example: GET /patients/123
    #   1. Look for file /patients/123 (not found)
    #   2. Look for directory /patients/123/ (not found)
    #   3. Serve /index.html (React Router takes over)
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets aggressively
    # JS/CSS files have content hashes (main.a1b2c3.js)
    # Safe to cache for 1 year because filenames change when content changes
    # "immutable" tells browser: this file will never change at this URL
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Health check endpoint for K8s probes
    # Returns 200 OK with body "ok"
    # K8s will hit this endpoint to verify container is healthy
    location /nginx-health {
        return 200 'ok';
        add_header Content-Type text/plain;
    }
}
```

### Why try_files for SPAs?

Traditional multi-page apps: each URL maps to a file on disk (`/about.html` serves `about.html`).

Single-page apps: one HTML file (`index.html`), JavaScript handles routing.

Without `try_files $uri $uri/ /index.html`:
- User visits `/patients/123` directly (refresh or bookmark)
- nginx looks for file `/patients/123` on disk
- File doesn't exist → 404 error

With `try_files`:
- nginx serves `index.html` for all routes
- React Router reads `/patients/123` from URL
- React Router renders the correct component

### Caching Strategy Explained

Static assets with content hashes:
- `main.a1b2c3d4.js` (hash changes when content changes)
- `styles.e5f6g7h8.css`

Safe to cache aggressively because:
- If you update code, Vite generates new filenames
- Browser never serves stale code (new HTML references new filenames)
- `Cache-Control: immutable` tells browser: never revalidate this file

HTML files (`index.html`):
- No caching (default nginx behavior)
- Browser always fetches latest version
- Latest HTML references latest JS/CSS filenames

## 5. .dockerignore Files

`.dockerignore` excludes files from Docker build context (similar to `.gitignore`).

### Why .dockerignore Matters

1. **Build speed:** Smaller context = faster upload to Docker daemon
2. **Security:** Prevents secrets from being baked into images
3. **Image size:** Prevents unnecessary files in final image

### Backend .dockerignore

```
# Virtual environment (we install fresh in container)
.venv

# Python cache files (not needed in container)
__pycache__
*.pyc

# Environment files (NEVER bake secrets into images)
.env
.env.*
.env.local
.env.production

# Test files (not needed in production image)
tests/
.pytest_cache

# Linter cache
.ruff_cache

# Documentation (reduces build context size)
*.md
README.md

# Git history (not needed in container)
.git
.gitignore

# IDE files
.vscode
.idea
*.swp
```

### Frontend .dockerignore

```
# Dependencies (we install fresh with npm ci)
node_modules

# Environment files (secrets don't belong in images)
.env
.env.*
.env.local
.env.production

# Build output (we build fresh in Dockerfile)
dist

# Documentation
*.md
README.md

# Git history
.git
.gitignore

# IDE files
.vscode
.idea
*.swp

# Test coverage reports
coverage
.nyc_output
```

### Security Example: Why Exclude .env

Bad scenario (no .dockerignore):
```bash
# .env contains secrets
DATABASE_URL=postgresql://user:password@prod-db/app
CLAUDE_API_KEY=sk-ant-...

# Build image
docker build -t myapp .

# .env is now baked into image layer
# Anyone with image access can extract secrets:
docker history myapp
docker save myapp -o myapp.tar
tar -xf myapp.tar
# Secrets exposed in layer files
```

Good scenario (with .dockerignore):
```bash
# .env excluded from build context
# Secrets injected at runtime via K8s Secrets
# Image contains no sensitive data
```

## 6. Artifact Registry Setup

GCP Artifact Registry stores Docker images securely with IAM integration.

### Create Repository

```bash
# Create a Docker repository named "doctor-app"
# Location: us-central1 (choose region near your GKE cluster)
gcloud artifacts repositories create doctor-app \
  --repository-format=docker \
  --location=us-central1 \
  --description="AI Doctor Assistant container images"

# Verify creation
gcloud artifacts repositories list --location=us-central1
```

### Configure Docker Authentication

```bash
# Configure Docker to authenticate with Artifact Registry
# This adds credential helper to ~/.docker/config.json
gcloud auth configure-docker us-central1-docker.pkg.dev

# Verify authentication
gcloud auth print-access-token | docker login -u oauth2accesstoken \
  --password-stdin https://us-central1-docker.pkg.dev
```

### Build and Push Images

```bash
# Replace PROJECT_ID with your GCP project ID
# Image name format: REGION-docker.pkg.dev/PROJECT/REPO/IMAGE:TAG
export PROJECT_ID=my-gcp-project

# Backend image
docker build -t us-central1-docker.pkg.dev/$PROJECT_ID/doctor-app/backend:v1.0.0 backend/
docker push us-central1-docker.pkg.dev/$PROJECT_ID/doctor-app/backend:v1.0.0

# Frontend image
docker build -t us-central1-docker.pkg.dev/$PROJECT_ID/doctor-app/frontend:v1.0.0 frontend/
docker push us-central1-docker.pkg.dev/$PROJECT_ID/doctor-app/frontend:v1.0.0

# Verify images in registry
gcloud artifacts docker images list us-central1-docker.pkg.dev/$PROJECT_ID/doctor-app
```

### Image Naming Convention

Full image URL structure:
```
us-central1-docker.pkg.dev/PROJECT_ID/doctor-app/backend:v1.0.0
│                │         │          │          │       │
│                │         │          │          │       └─ Tag
│                │         │          │          └──────── Image name
│                │         │          └─────────────────── Repository
│                │         └────────────────────────────── Project ID
│                └──────────────────────────────────────── Region
└───────────────────────────────────────────────────────── Registry domain
```

## 7. GitHub Actions: CI Workflow (Pull Requests)

The CI workflow runs on every pull request to validate code quality and buildability.

`.github/workflows/ci.yaml`:

```yaml
name: CI

# Trigger on pull requests to main branch
on:
  pull_request:
    branches: [ main ]

# Allow multiple jobs to run in parallel
jobs:
  # Backend linting with ruff
  lint-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v1
        with:
          version: "latest"

      - name: Set up Python 3.12
        run: uv python install 3.12

      - name: Install dependencies
        working-directory: ./backend
        run: uv sync --frozen --no-dev

      - name: Lint with ruff
        working-directory: ./backend
        run: |
          uv run ruff check .
          uv run ruff format --check .

  # Backend tests with pytest
  test-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v1
        with:
          version: "latest"

      - name: Set up Python 3.12
        run: uv python install 3.12

      - name: Install dependencies (including dev)
        working-directory: ./backend
        run: uv sync --frozen

      - name: Run tests
        working-directory: ./backend
        run: uv run pytest -v

  # Frontend linting with ESLint
  lint-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        working-directory: ./frontend
        run: npm ci

      - name: Lint with ESLint
        working-directory: ./frontend
        run: npm run lint

  # Frontend tests with Vitest
  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        working-directory: ./frontend
        run: npm ci

      - name: Run tests
        working-directory: ./frontend
        run: npm test

  # Verify Docker images build successfully
  # Don't push — just validate Dockerfiles
  build-images:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build backend image
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          push: false
          tags: backend:pr-${{ github.event.pull_request.number }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build frontend image
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          push: false
          tags: frontend:pr-${{ github.event.pull_request.number }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### CI Workflow Explained

**Parallel Execution:** All jobs run simultaneously (5 jobs in ~3-4 minutes vs ~15 minutes sequential).

**working-directory:** Each job operates in backend/ or frontend/ subdirectory (monorepo pattern).

**uv sync --frozen:** Fails if lock file is out of sync (prevents "works on my machine" issues).

**npm ci vs npm install:** `ci` does clean install from lock file (reproducible), `install` may update lock.

**Docker build caching:** `cache-from: type=gha` reuses layers from previous builds (faster subsequent builds).

**Why not push images?** CI validates builds work. CD (next section) pushes images.

## 8. GitHub Actions: CD Workflow (Deploy to Production)

The CD workflow runs when code merges to main, building and deploying to GKE.

`.github/workflows/cd.yaml`:

```yaml
name: CD

# Trigger on pushes to main (i.e., merged PRs)
on:
  push:
    branches: [ main ]

env:
  PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
  GKE_CLUSTER: doctor-app-cluster
  GKE_ZONE: us-central1
  REGISTRY: us-central1-docker.pkg.dev

jobs:
  deploy:
    runs-on: ubuntu-latest

    # Required for Workload Identity Federation
    permissions:
      contents: 'read'
      id-token: 'write'

    steps:
      - uses: actions/checkout@v4

      # Authenticate to GCP using Workload Identity Federation
      # No service account keys needed
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
          service_account: ${{ secrets.WIF_SERVICE_ACCOUNT }}

      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2

      # Configure Docker to push to Artifact Registry
      - name: Configure Docker
        run: gcloud auth configure-docker ${{ env.REGISTRY }}

      # Get GKE credentials for kubectl
      - name: Get GKE credentials
        run: |
          gcloud container clusters get-credentials ${{ env.GKE_CLUSTER }} \
            --zone ${{ env.GKE_ZONE }}

      # Build and push backend image
      # Tag with git SHA for traceability
      - name: Build and push backend
        run: |
          IMAGE=${{ env.REGISTRY }}/${{ env.PROJECT_ID }}/doctor-app/backend
          docker build -t $IMAGE:${{ github.sha }} backend/
          docker tag $IMAGE:${{ github.sha }} $IMAGE:latest
          docker push $IMAGE:${{ github.sha }}
          docker push $IMAGE:latest

      # Build and push frontend image
      - name: Build and push frontend
        run: |
          IMAGE=${{ env.REGISTRY }}/${{ env.PROJECT_ID }}/doctor-app/frontend
          docker build -t $IMAGE:${{ github.sha }} frontend/
          docker tag $IMAGE:${{ github.sha }} $IMAGE:latest
          docker push $IMAGE:${{ github.sha }}
          docker push $IMAGE:latest

      # Update Kustomize overlays with new image tags
      - name: Update Kustomization
        working-directory: ./k8s/overlays/production
        run: |
          kustomize edit set image \
            backend=${{ env.REGISTRY }}/${{ env.PROJECT_ID }}/doctor-app/backend:${{ github.sha }} \
            frontend=${{ env.REGISTRY }}/${{ env.PROJECT_ID }}/doctor-app/frontend:${{ github.sha }}

      # Deploy to GKE
      - name: Deploy to GKE
        run: |
          kubectl apply -k k8s/overlays/production
          kubectl rollout status deployment/doctor-backend -n doctor-app --timeout=5m
          kubectl rollout status deployment/doctor-frontend -n doctor-app --timeout=5m

      # Verify deployment health
      - name: Verify deployment
        run: |
          kubectl get pods -n doctor-app
          kubectl get services -n doctor-app
```

### CD Workflow Explained

**Trigger:** Only runs when code merges to main (not on every commit).

**Workload Identity Federation:** Authenticates GitHub Actions to GCP without service account keys (see next section).

**Image tagging:** Every build gets two tags:
- `${{ github.sha }}`: Git commit SHA (e.g., `abc1234567`) for traceability
- `latest`: Convenient reference to most recent build

**Kustomize edit:** Updates image tags in K8s manifests programmatically (avoids manual editing).

**kubectl apply -k:** Applies manifests from `k8s/overlays/production` (Kustomize overlay).

**rollout status:** Waits for deployment to complete before marking workflow successful (catches deployment failures).

**Timeout:** If deployment doesn't complete in 5 minutes, fail the workflow (prevents hanging workflows).

## 9. Workload Identity Federation (WIF)

Workload Identity Federation eliminates the need for long-lived service account keys.

### The Problem with Service Account Keys

Old approach:
1. Create GCP service account
2. Generate JSON key file
3. Store key in GitHub Secrets
4. GitHub Actions uses key to authenticate

Issues:
- Key never expires (security risk)
- Manual rotation required
- Key leak = full GCP access
- No audit trail of which workflow used key

### How Workload Identity Federation Works

```
GitHub Actions                GCP
────────────────────────────────────────
Workflow runs
  │
  ├─ GitHub issues OIDC token
  │  (cryptographically signed, short-lived)
  │
  └─→ Send OIDC token to GCP
                │
                ├─ GCP validates token signature
                │  (verifies it's from GitHub)
                │
                ├─ Checks token claims:
                │  - Repository: anthropic/ai-doctor-assistant
                │  - Branch: main
                │  - Actor: octocat
                │
                └─→ GCP issues short-lived access token
                    (expires in 1 hour)

GitHub Actions uses token to push images, deploy
```

### Setup Workload Identity Federation

```bash
# 1. Enable required APIs
gcloud services enable iamcredentials.googleapis.com
gcloud services enable sts.googleapis.com

# 2. Create Workload Identity Pool
gcloud iam workload-identity-pools create github-pool \
  --location=global \
  --description="Pool for GitHub Actions"

# 3. Create Workload Identity Provider
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" \
  --attribute-condition="assertion.repository=='YOUR_ORG/ai-doctor-assistant'"

# 4. Create Service Account for GitHub Actions
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions deployer"

# 5. Grant necessary permissions to service account
PROJECT_ID=$(gcloud config get-value project)

# Allow pushing images to Artifact Registry
gcloud artifacts repositories add-iam-policy-binding doctor-app \
  --location=us-central1 \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

# Allow deploying to GKE
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/container.developer"

# 6. Allow GitHub to impersonate service account
gcloud iam service-accounts add-iam-policy-binding \
  github-actions@${PROJECT_ID}.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_ORG/ai-doctor-assistant"

# 7. Get Workload Identity Provider ID for GitHub Secrets
gcloud iam workload-identity-pools providers describe github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --format="value(name)"

# Output (save to GitHub Secrets as WIF_PROVIDER):
# projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider
```

### GitHub Secrets Configuration

Add these secrets to your GitHub repository (Settings → Secrets → Actions):

- `GCP_PROJECT_ID`: Your GCP project ID (e.g., `my-gcp-project`)
- `WIF_PROVIDER`: Workload Identity Provider ID (from step 7 above)
- `WIF_SERVICE_ACCOUNT`: Service account email (`github-actions@PROJECT_ID.iam.gserviceaccount.com`)

### Benefits of WIF

1. **No long-lived credentials:** OIDC tokens expire in minutes
2. **Automatic rotation:** New token issued per workflow run
3. **Fine-grained access control:** Restrict by repository, branch, actor
4. **Audit trail:** Cloud Logging shows which workflow accessed what
5. **Leak-resistant:** Even if token leaks, expires quickly and scoped to specific repo

## 10. Image Tagging Strategy

Effective tagging enables traceability, rollbacks, and environment promotion.

### Tagging Schemes

| Tag Type | Example | When Applied | Use Case |
|----------|---------|--------------|----------|
| Git SHA | `backend:a1b2c3d4` | Every build | Traceability: know exactly which commit is deployed |
| `latest` | `backend:latest` | Every main build | Convenience: dev/staging can pull latest automatically |
| Semver | `backend:v1.2.3` | Releases | Production: semantic versioning, clear version history |
| Branch | `backend:feature-auth` | Feature branches | Testing: deploy feature branch to preview environment |
| Environment | `backend:staging` | Promotion | Tagging: mark image as validated for environment |

### Recommended Strategy

**Development:**
```bash
# Tag with git SHA (main identifier)
docker tag backend:local backend:$(git rev-parse --short HEAD)

# Tag with latest (convenience)
docker tag backend:local backend:latest

# Push both
docker push backend:$(git rev-parse --short HEAD)
docker push backend:latest
```

**Staging:**
```bash
# After validating in dev, promote to staging
docker tag backend:a1b2c3d4 backend:staging
docker push backend:staging

# Update K8s manifests to use staging tag
kubectl set image deployment/doctor-backend backend=backend:staging -n doctor-app-staging
```

**Production:**
```bash
# After validating in staging, tag with semver
docker tag backend:a1b2c3d4 backend:v1.2.3
docker push backend:v1.2.3

# Update K8s manifests to use specific version
kubectl set image deployment/doctor-backend backend=backend:v1.2.3 -n doctor-app
```

### Why Multiple Tags?

Single image, multiple tags pointing to same digest:

```bash
# List all tags for an image digest
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/PROJECT/doctor-app/backend \
  --include-tags \
  --filter="digest=sha256:a1b2c3d4..."

# Output:
# backend:a1b2c3d4      sha256:a1b2c3d4...
# backend:latest        sha256:a1b2c3d4...
# backend:v1.2.3        sha256:a1b2c3d4...
# backend:staging       sha256:a1b2c3d4...
```

Same image content, different semantic meanings:
- `a1b2c3d4`: "This is commit a1b2c3d4"
- `latest`: "This is the most recent main build"
- `v1.2.3`: "This is release version 1.2.3"
- `staging`: "This is validated for staging"

## 11. Rollback Strategies

When a deployment goes wrong, quick rollback is critical.

### Strategy 1: kubectl rollout undo (Fastest)

Roll back to previous ReplicaSet:

```bash
# Immediate rollback (takes 30-60 seconds)
kubectl rollout undo deployment/doctor-backend -n doctor-app

# Rollback to specific revision
kubectl rollout history deployment/doctor-backend -n doctor-app
kubectl rollout undo deployment/doctor-backend --to-revision=3 -n doctor-app

# Monitor rollback progress
kubectl rollout status deployment/doctor-backend -n doctor-app
```

**How it works:**
- Kubernetes keeps old ReplicaSets (default: 10 revisions)
- `undo` scales up previous ReplicaSet, scales down current one
- No new image build/push required

**Pros:**
- Fastest rollback (seconds)
- No CI/CD pipeline involved
- Works even if Artifact Registry is down

**Cons:**
- Only works for last 10 deployments (by default)
- Doesn't update Git manifests (drift between Git and cluster)
- Manual operation (error-prone under pressure)

### Strategy 2: Revert Git Commit + Redeploy

Revert the problematic commit and let CI/CD redeploy:

```bash
# 1. Find the bad commit
git log --oneline

# Output:
# a1b2c3d (HEAD -> main) feat: add new feature (BAD)
# e5f6g7h fix: improve validation
# i9j0k1l feat: refactor auth

# 2. Revert the commit
git revert a1b2c3d
git push origin main

# 3. CI/CD automatically builds and deploys reverted state
# (takes 5-10 minutes)
```

**Pros:**
- Git remains source of truth (no drift)
- Audit trail of rollback in Git history
- Automated deployment via CI/CD

**Cons:**
- Slower (must wait for CI/CD pipeline)
- Requires CI/CD to be operational

### Strategy 3: Update Manifest to Previous Image Tag

Manually update Kubernetes manifests to use previous image:

```bash
# 1. Identify current and previous image
kubectl describe deployment/doctor-backend -n doctor-app | grep Image
# Output: Image: backend:a1b2c3d4 (current, broken)

# Check Artifact Registry for previous tag
gcloud artifacts docker images list backend --sort-by=~CREATE_TIME --limit=5
# Output: backend:e5f6g7h8 (previous, known good)

# 2. Update Kustomization
cd k8s/overlays/production
kustomize edit set image backend=backend:e5f6g7h8

# 3. Apply updated manifest
kubectl apply -k k8s/overlays/production

# 4. Commit rollback to Git
git add k8s/overlays/production/kustomization.yaml
git commit -m "rollback: revert backend to e5f6g7h8"
git push
```

**Pros:**
- Full control over which version to deploy
- Can skip multiple versions (e.g., rollback 5 releases)
- Updates Git manifests (no drift)

**Cons:**
- Manual process (slower)
- Requires knowing previous good image tag

### Strategy 4: GitOps with ArgoCD (Automated)

If using ArgoCD (GitOps tool):

```bash
# 1. Revert Git commit
git revert a1b2c3d
git push origin main

# 2. ArgoCD detects Git change and auto-syncs
# (deploys reverted state automatically)

# 3. Monitor in ArgoCD UI
# ArgoCD shows sync status and health
```

**Pros:**
- Git is single source of truth
- Automatic sync (no manual kubectl)
- Full audit trail
- Can preview changes before applying

**Cons:**
- Requires ArgoCD setup
- Slightly slower (ArgoCD sync interval ~3 minutes)

### Rollback Decision Tree

```
Is cluster state critical?
├─ YES (production outage)
│   └─→ kubectl rollout undo
│       (fastest: 30-60 seconds)
│
└─ NO (minor issue, staging environment)
    └─→ Is CI/CD operational?
        ├─ YES
        │   └─→ git revert + push
        │       (clean, automated, 5-10 minutes)
        │
        └─ NO
            └─→ Manual manifest update
                (full control, slower)
```

### Preventing Rollbacks: Deployment Safety

Best practices to reduce need for rollbacks:

1. **Canary deployments:** Deploy to 10% of pods first, monitor, then roll out
2. **Blue-green deployments:** Deploy new version alongside old, switch traffic atomically
3. **Progressive delivery:** Gradually increase traffic to new version using Flagger/Argo Rollouts
4. **Automated rollbacks:** Use readiness probes + HPA to auto-rollback on errors
5. **Staging validation:** Require successful staging deployment before production

### Deployment History

View past deployments and image tags:

```bash
# Deployment history (last 10 revisions)
kubectl rollout history deployment/doctor-backend -n doctor-app

# Output:
# REVISION  CHANGE-CAUSE
# 1         Initial deployment
# 2         Update to v1.0.1
# 3         Update to v1.0.2 (current)

# Detailed info on specific revision
kubectl rollout history deployment/doctor-backend --revision=2 -n doctor-app

# Output shows full deployment spec including image tag
```

### Configuring Revision History Limit

By default, Kubernetes keeps 10 old ReplicaSets. Adjust in Deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: doctor-backend
spec:
  # Keep last 15 deployments for rollback
  revisionHistoryLimit: 15
  # ...
```

Considerations:
- Higher limit = more rollback options, but more cluster memory used
- Lower limit = less rollback flexibility
- Recommended: 10-15 for production, 3-5 for dev

## Summary

This document covered the complete deployment pipeline:

1. **Multi-stage Dockerfiles:** Minimal production images (~150MB backend, ~90MB frontend)
2. **nginx for SPAs:** Proper SPA routing with `try_files` and aggressive asset caching
3. **Artifact Registry:** Secure image storage with IAM integration
4. **CI Workflow:** Parallel linting, testing, and build validation on PRs
5. **CD Workflow:** Automated build, push, and deploy on merge to main
6. **Workload Identity Federation:** Secure authentication without service account keys
7. **Image Tagging:** Multi-tag strategy for traceability and environment promotion
8. **Rollback Strategies:** Four approaches with trade-offs for different scenarios

Next document: Secret Management — how to securely inject secrets at runtime (no secrets in images).
