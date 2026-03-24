# Docker Compose Reference & Container Operations

> **Document 14** in the [Infrastructure & Kubernetes Learning Guide](./00-OVERVIEW.md)
>
> **Purpose:** Practical reference for Docker Compose as used in this project -- how volumes, naming, and networking work, how to inspect data inside containers, and the commands that matter for daily development. Written after a real incident where a directory rename caused silent data loss.
>
> **Prerequisites:** Docker installed and running. Familiarity with the AI Doctor Assistant's architecture (FastAPI backend + React frontend + PostgreSQL + Qdrant).

---

## Table of Contents

1. [Our Docker Compose Setup](#1-our-docker-compose-setup)
2. [How Docker Compose Names Things](#2-how-docker-compose-names-things)
3. [Volumes -- Where Data Actually Lives](#3-volumes--where-data-actually-lives)
4. [Container Lifecycle Commands](#4-container-lifecycle-commands)
5. [Inspecting Data Inside Containers](#5-inspecting-data-inside-containers)
6. [PostgreSQL Container Operations](#6-postgresql-container-operations)
7. [Qdrant Container Operations](#7-qdrant-container-operations)
8. [Networking Fundamentals](#8-networking-fundamentals)
9. [Debugging and Troubleshooting](#9-debugging-and-troubleshooting)
10. [Lessons Learned -- The Directory Rename Incident](#10-lessons-learned--the-directory-rename-incident)

---

## 1. Our Docker Compose Setup

The project's `docker-compose.yml` at the repo root defines two services:

```yaml
services:
  postgres:
    image: postgres:16
    container_name: build_ai_agents_db
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: build_ai_agents
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  qdrant:
    image: qdrant/qdrant:v1.12.1
    container_name: build_ai_agents_qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

volumes:
  pgdata:
  qdrant_data:
```

What each section does:

- **`services`** -- Each entry defines a container. `postgres` and `qdrant` are service names used for inter-container DNS.
- **`container_name`** -- Overrides the default auto-generated name. Without this, Compose would name them `build-ai-agents-postgres-1`.
- **`environment`** -- Environment variables passed into the container. PostgreSQL uses these to create the initial database and user on first startup.
- **`ports`** -- Maps `host:container`. `"5432:5432"` means your Mac's port 5432 forwards to the container's 5432.
- **`volumes`** -- Named volumes for persistent data. This is the most important section -- see [Section 3](#3-volumes--where-data-actually-lives).
- **`restart: unless-stopped`** -- Qdrant auto-restarts if it crashes, unless you explicitly stop it with `docker compose stop`.

---

## 2. How Docker Compose Names Things

**This is the most common source of confusion.** Docker Compose prefixes all resources (volumes, networks, containers) with a **project name**. By default, the project name is the **name of the parent directory** where `docker-compose.yml` lives.

```
Directory: build-ai-agents/
  Volume names:  build-ai-agents_pgdata, build-ai-agents_qdrant_data
  Network name:  build-ai-agents_default

Directory: build-ai-agents-rag/
  Volume names:  build-ai-agents-rag_pgdata, build-ai-agents-rag_qdrant_data
  Network name:  build-ai-agents-rag_default
```

**If you rename the directory, move the project, or run Compose from a different path**, Docker creates entirely new volumes with the new prefix. It does not know that `build-ai-agents-rag_pgdata` and `build-ai-agents_pgdata` are "the same thing." To Docker, they are completely separate.

### Locking the project name

Add `COMPOSE_PROJECT_NAME` to the `.env` file next to `docker-compose.yml`:

```
COMPOSE_PROJECT_NAME=build-ai-agents
```

This ensures the project name is always `build-ai-agents` regardless of directory name. Alternatively, pass it at runtime:

```bash
docker compose -p build-ai-agents up -d
```

### How to see the current project name

```bash
docker compose config | head -2
# Output: name: build-ai-agents
```

---

## 3. Volumes -- Where Data Actually Lives

### Named volumes vs bind mounts

Docker has two volume types:

| Type | Syntax | Managed by | Location |
|------|--------|-----------|----------|
| **Named volume** | `pgdata:/var/lib/postgresql/data` | Docker | `/var/lib/docker/volumes/build-ai-agents_pgdata/_data` |
| **Bind mount** | `./data:/var/lib/postgresql/data` | You | Your local filesystem |

Our project uses **named volumes**. Docker manages the storage location, and volumes survive container deletion.

### Volume lifecycle -- what survives what

| Action | Container | Volume | Data |
|--------|-----------|--------|------|
| `docker compose stop` | Stopped (preserved) | Kept | Safe |
| `docker compose down` | Removed | **Kept** | Safe |
| `docker compose down -v` | Removed | **Removed** | **Gone** |
| `docker rm <container>` | Removed | Kept | Safe |
| `docker volume rm <vol>` | N/A | **Removed** | **Gone** |

**Key takeaway:** `docker compose down` (without `-v`) is always safe. The `-v` flag is the destructive one.

### Listing and inspecting volumes

```bash
# List all volumes
docker volume ls

# Filter for project volumes
docker volume ls | grep build-ai-agents

# Inspect a specific volume (creation date, mount point)
docker volume inspect build-ai-agents_pgdata

# Check size of data in a volume
docker run --rm -v build-ai-agents_pgdata:/data alpine du -sh /data

# Browse files in a volume
docker run --rm -v build-ai-agents_pgdata:/data alpine ls -la /data
```

### Copying data between volumes

If you need to migrate data from one volume to another (e.g., after a directory rename):

```bash
docker compose stop

# Copy from old volume to new
docker run --rm \
  -v build-ai-agents-rag_pgdata:/src \
  -v build-ai-agents_pgdata:/dst \
  alpine sh -c "rm -rf /dst/* && cp -a /src/. /dst/"

docker compose up -d
```

---

## 4. Container Lifecycle Commands

### Starting and stopping

```bash
# Start services (foreground -- logs stream to terminal, Ctrl+C stops them)
docker compose up

# Start services (detached -- runs in background)
docker compose up -d

# Stop without removing (containers go to "stopped" state)
docker compose stop

# Start previously stopped containers
docker compose start

# Stop + remove containers (volumes preserved)
docker compose down

# Stop + remove containers AND volumes (DATA LOSS)
docker compose down -v

# Restart a single service
docker compose restart postgres

# Recreate containers (useful after image updates)
docker compose up -d --force-recreate

# Recreate and rebuild (if using custom Dockerfiles)
docker compose up -d --build
```

### Viewing status

```bash
# Running containers for this project
docker compose ps

# All containers (including stopped)
docker ps -a

# Container resource usage (CPU, memory)
docker stats --no-stream

# Follow logs for all services
docker compose logs -f

# Follow logs for a specific service
docker compose logs -f postgres

# Last 50 lines of logs
docker compose logs --tail 50 qdrant
```

### When containers refuse to start

If you see "container name already exists" after a Docker restart:

```bash
# Option 1: Force recreate (preserves volumes)
docker compose up -d --force-recreate

# Option 2: Remove stopped containers first, then start
docker compose down && docker compose up -d

# DO NOT use docker rm unless you understand volume naming
```

---

## 5. Inspecting Data Inside Containers

### Getting a shell

```bash
# Interactive bash shell inside a running container
docker exec -it build_ai_agents_db bash

# If bash isn't available (minimal images), use sh
docker exec -it build_ai_agents_qdrant sh

# Run a single command without entering the container
docker exec build_ai_agents_db ls /var/lib/postgresql/data
```

The `-it` flags mean **interactive** + **TTY** (gives you a proper terminal). Without them, you get a non-interactive session that is useful for scripting but not for exploring.

### Checking what is mounted where

```bash
# See all mounts for a container (pretty-printed)
docker inspect build_ai_agents_db --format '{{json .Mounts}}' | jq

# Quick volume-to-path mapping
docker inspect build_ai_agents_db | jq -r '.[0].Mounts[] | select(.Name) | "\(.Name) → \(.Destination)"'
```

---

## 6. PostgreSQL Container Operations

PostgreSQL has **psql**, an interactive command-line client built into the container. This is the primary tool for inspecting data.

### Connecting to psql

```bash
# Enter psql directly (most useful)
docker exec -it build_ai_agents_db psql -U user -d build_ai_agents

# Or from a shell inside the container
docker exec -it build_ai_agents_db bash
$ psql -U user -d build_ai_agents
```

### Essential psql commands

Inside `psql`, commands starting with `\` are meta-commands (psql-specific), and everything else is SQL:

```
\l                     -- list all databases
\dt                    -- list tables in current database
\d patients            -- describe the 'patients' table (columns, types, constraints)
\d+ patients           -- same but with extra detail (storage, comments)
\du                    -- list database users/roles
\dn                    -- list schemas
\di                    -- list indexes
\df                    -- list functions
\x                     -- toggle expanded display (vertical output for wide rows)
\timing                -- toggle query timing
\q                     -- quit psql
```

### Common queries for inspection

```sql
-- Count rows
SELECT count(*) FROM patients;

-- See all data (use LIMIT for large tables)
SELECT * FROM patients LIMIT 10;

-- Check table size on disk
SELECT pg_size_pretty(pg_total_relation_size('patients'));

-- See all tables with row counts
SELECT schemaname, relname, n_live_tup
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;

-- Check active connections
SELECT pid, usename, datname, state, query
FROM pg_stat_activity
WHERE datname = 'build_ai_agents';
```

### Running SQL without entering psql

```bash
# One-liner from your host terminal
docker exec build_ai_agents_db psql -U user -d build_ai_agents -c "SELECT id, name FROM patients;"

# Run a SQL file
docker exec -i build_ai_agents_db psql -U user -d build_ai_agents < seed.sql
```

### Backup and restore

```bash
# Dump the database to a local file
docker exec build_ai_agents_db pg_dump -U user build_ai_agents > backup.sql

# Restore from a dump file
docker exec -i build_ai_agents_db psql -U user -d build_ai_agents < backup.sql
```

---

## 7. Qdrant Container Operations

**Qdrant has no interactive CLI like psql.** The `qdrant` binary inside the container is the server process only -- it has no shell or query subcommands. This is by design: Qdrant is an API-first vector database where all interaction happens through HTTP REST (port 6333) or gRPC (port 6334).

### Why no CLI?

Unlike relational databases where you frequently write ad-hoc SQL queries, vector databases are consumed programmatically. You don't manually browse embeddings -- they are 1536-dimensional float arrays that are meaningless to read. The operations that matter (insert, search, delete) are always done from application code. Qdrant's REST API is the "CLI."

### Inspecting via REST API (curl)

All commands below run from your **host machine** (not inside the container), since port 6333 is mapped:

```bash
# List all collections
curl -s http://localhost:6333/collections | jq

# Get collection details (schema, vector config, point count)
curl -s http://localhost:6333/collections/clinical_guidelines | jq

# Browse points (vectors + payloads) in a collection
curl -s -X POST http://localhost:6333/collections/clinical_guidelines/points/scroll \
  -H "Content-Type: application/json" \
  -d '{"limit": 5, "with_payload": true, "with_vector": false}' | jq

# Count points in a collection
curl -s -X POST http://localhost:6333/collections/clinical_guidelines/points/count \
  -H "Content-Type: application/json" \
  -d '{}' | jq

# Search for similar vectors (replace the vector with a real embedding)
curl -s -X POST http://localhost:6333/collections/clinical_guidelines/points/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": [0.1, 0.2, ...],
    "limit": 3,
    "with_payload": true
  }' | jq

# Get a specific point by ID
curl -s http://localhost:6333/collections/clinical_guidelines/points/1 | jq

# Health check
curl -s http://localhost:6333/healthz

# Qdrant server info (version, commit)
curl -s http://localhost:6333 | jq
```

### Inspecting via Python (from your app's venv)

If you have the Qdrant Python client installed:

```python
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)

# List collections
print(client.get_collections())

# Get collection info
print(client.get_collection("clinical_guidelines"))

# Browse points
points = client.scroll(collection_name="clinical_guidelines", limit=5, with_payload=True, with_vectors=False)
for point in points[0]:
    print(f"ID: {point.id}, Payload: {point.payload}")
```

### Qdrant Web Dashboard

Qdrant ships with a built-in web UI. Open in your browser:

```
http://localhost:6333/dashboard
```

This provides a visual interface to browse collections, view points, and run test queries. It is the closest thing to a psql-like interactive experience for Qdrant.

---

## 8. Networking Fundamentals

### How Docker Compose networking works

When you run `docker compose up`, Compose creates a **bridge network** for the project. All services join this network and can reach each other by **service name** as hostname.

```
┌─────────────────────────────────────────────┐
│        build-ai-agents_default network      │
│                                             │
│  ┌──────────┐           ┌──────────┐        │
│  │ postgres │           │  qdrant  │        │
│  │ :5432    │           │ :6333    │        │
│  │          │           │ :6334    │        │
│  └──────────┘           └──────────┘        │
│                                             │
└───────┬─────────────────────────┬───────────┘
        │ 5432:5432               │ 6333:6333, 6334:6334
        ▼                         ▼
   Host (your Mac)           Host (your Mac)
   localhost:5432            localhost:6333
```

**Inside the Docker network**, containers reach each other by service name:
- `postgres:5432` (not `localhost`)
- `qdrant:6333` (not `localhost`)

**From your Mac (host)**, you use `localhost` because of the port mappings.

**From your FastAPI app** (running outside Docker via `uv run uvicorn`), you use `localhost` because the app is on the host, not inside Docker.

### Viewing the network

```bash
# List networks
docker network ls | grep build-ai-agents

# Inspect network (see connected containers and IPs)
docker network inspect build-ai-agents_default

# Check which ports are mapped
docker compose ps --format "table {{.Name}}\t{{.Ports}}"
```

### Common networking issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Connection refused` on localhost:5432 | Container not running or port not mapped | `docker compose ps` to check status |
| App can't connect to DB | Using wrong hostname | Use `localhost` from host, service name from inside Docker |
| Port already in use | Another process on the same port | `lsof -i :5432` to find it, or change the host port in compose |

---

## 9. Debugging and Troubleshooting

### Container won't start

```bash
# Check logs for error messages
docker compose logs postgres

# Check if port is already in use
lsof -i :5432
lsof -i :6333

# Check Docker disk space
docker system df

# Remove unused images/containers/networks (not volumes)
docker system prune
```

### Container keeps restarting

```bash
# Check exit code
docker inspect build_ai_agents_db --format '{{.State.ExitCode}}'

# Exit code meanings:
# 0   = clean shutdown
# 1   = application error
# 137 = OOM killed (out of memory)
# 143 = SIGTERM (graceful stop)

# Check resource limits
docker stats --no-stream
```

### Data appears missing

Before panicking:

```bash
# 1. Check which volumes exist
docker volume ls | grep -E "pgdata|qdrant"

# 2. Check what the running container is actually using
docker inspect build_ai_agents_db --format '{{json .Mounts}}' | jq

# 3. If multiple volumes exist, check each for data
docker run --rm -v VOLUME_NAME:/data alpine du -sh /data

# 4. The volume with the most data is likely your old one
```

---

## 10. Lessons Learned -- The Directory Rename Incident

### What happened

1. Project was developed in a directory named `build-ai-agents-rag/`. Docker Compose created volumes `build-ai-agents-rag_pgdata` and `build-ai-agents-rag_qdrant_data` with 5 patients and the `clinical_guidelines` collection.

2. The directory was later renamed to `build-ai-agents/`. Docker had no way to know this was the same project.

3. Docker was restarted (after a macOS split-screen event). Containers went to "stopped" state.

4. `docker compose up` failed with "container name already exists" because the old stopped containers were still registered under the same `container_name`.

5. `docker rm` was used to remove the stopped containers. This removed the containers but preserved the volumes.

6. `docker compose up` created new containers with new volumes (`build-ai-agents_pgdata`, `build-ai-agents_qdrant_data`). These were empty.

7. The old data still existed in the `build-ai-agents-rag_*` volumes the entire time.

### How to prevent this

1. **Set `COMPOSE_PROJECT_NAME`** in `.env` (see [Section 2](#2-how-docker-compose-names-things)). This locks the volume prefix.

2. **Use `docker compose down` + `docker compose up -d`** instead of `docker rm`. Compose understands its own resources; raw `docker rm` does not.

3. **When you see "container name exists"**, use `docker compose up -d --force-recreate` -- not `docker rm`.

4. **Before deleting anything**, check `docker volume ls` to understand what exists and what's attached.

### Recovery process

Data was recovered by copying from old volumes to new:

```bash
docker compose stop

docker run --rm \
  -v build-ai-agents-rag_pgdata:/src \
  -v build-ai-agents_pgdata:/dst \
  alpine sh -c "rm -rf /dst/* && cp -a /src/. /dst/"

docker run --rm \
  -v build-ai-agents-rag_qdrant_data:/src \
  -v build-ai-agents_qdrant_data:/dst \
  alpine sh -c "rm -rf /dst/* && cp -a /src/. /dst/"

docker compose up -d
```

---

## Quick Reference Card

### Daily commands

| What | Command |
|------|---------|
| Start everything | `docker compose up -d` |
| Stop everything | `docker compose stop` |
| View logs | `docker compose logs -f` |
| Check status | `docker compose ps` |
| Restart a service | `docker compose restart postgres` |

### Data inspection

| What | Command |
|------|---------|
| Postgres shell | `docker exec -it build_ai_agents_db psql -U user -d build_ai_agents` |
| List tables | `\dt` (inside psql) |
| Describe table | `\d patients` (inside psql) |
| Qdrant collections | `curl -s http://localhost:6333/collections \| jq` |
| Qdrant dashboard | Open `http://localhost:6333/dashboard` in browser |
| Browse Qdrant points | `curl -s -X POST http://localhost:6333/collections/clinical_guidelines/points/scroll -H "Content-Type: application/json" -d '{"limit": 5, "with_payload": true, "with_vector": false}' \| jq` |

### Emergency commands

| What | Command |
|------|---------|
| Something won't start | `docker compose up -d --force-recreate` |
| Check all volumes | `docker volume ls` |
| Check what a container uses | `docker inspect CONTAINER --format '{{json .Mounts}}'` |
| Backup Postgres | `docker exec build_ai_agents_db pg_dump -U user build_ai_agents > backup.sql` |
| Nuclear reset (DATA LOSS) | `docker compose down -v && docker compose up -d` |