# FastAPI's Async Architecture

**Part 3 of 5: Async Server Architecture Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Learning Objectives](#learning-objectives)
2. [uvicorn and ASGI](#1-uvicorn-and-asgi)
3. [`async def` vs `def` Endpoints](#2-async-def-vs-def-endpoints)
4. [Dependency Injection and Async](#3-dependency-injection-and-async)
5. [SQLAlchemy Async](#4-sqlalchemy-async)
6. [Concurrency Under Load](#5-concurrency-under-load)
7. [The Claude Agent SDK `async for` Pattern](#6-the-claude-agent-sdk-async-for-pattern)
8. [Summary](#7-summary)

---

## Learning Objectives

After reading this document, you will understand:

- How **uvicorn** creates the event loop and dispatches requests to FastAPI via **ASGI**
- The critical difference between `async def` and `def` endpoints in FastAPI -- and why choosing wrong silently kills performance
- How FastAPI's **dependency injection** (`Depends`) works with async generators
- How **SQLAlchemy async** (`AsyncSession`, `create_async_engine`) integrates with the event loop
- Why **uvicorn workers** add multi-core parallelism on top of async I/O concurrency
- How the Claude Agent SDK's **`async for` pattern** works as an async iterator

Key mental models to internalize:

- **uvicorn is the event loop owner.** FastAPI is a framework that runs inside it. Your endpoint coroutines are scheduled by uvicorn's event loop. You never create the loop.
- **`async def` and `def` endpoints have completely different execution models.** `async def` runs on the event loop. `def` runs in a thread pool. Know which you are writing and why.
- The request lifecycle is: **uvicorn receives bytes → parses HTTP → calls ASGI app (FastAPI) → resolves dependencies → runs endpoint → serializes response → sends bytes.**

Common misconceptions to avoid:

- "FastAPI is inherently async" -- The framework supports both async and sync endpoints. Sync endpoints use a threadpool to avoid blocking the event loop. You must choose `async def` deliberately.
- "More uvicorn workers always helps" -- Workers help CPU-bound work and multi-core utilization. For I/O-bound work, a single worker with async handles many concurrent requests.
- "I need to manage the event loop" -- For most endpoints, just use `async def` and `await`. uvicorn and Starlette handle the loop, the ASGI interface, and the HTTP parsing.

---

## 1. uvicorn and ASGI

### What Happens When You Start the Server

```bash
cd backend && uv run uvicorn src.main:app --reload
```

This command:

1. **uvicorn starts** and creates an event loop (using `uvloop` on Linux/macOS for performance, or `asyncio` on Windows)
2. **Imports `src.main:app`** -- your FastAPI application object
3. **Runs the ASGI lifespan** -- calls your `@asynccontextmanager` startup/shutdown hooks
4. **Begins listening** on port 8000 for TCP connections
5. **For each HTTP request**: parses it, calls `app(scope, receive, send)` (the ASGI interface), and sends the response

### The Request Flow

```
TCP Connection
      │
      ▼
┌───────────────┐
│   uvicorn     │  Owns the event loop. Parses HTTP. Manages connections.
│   (server)    │
└───────┬───────┘
        │  ASGI protocol: app(scope, receive, send)
        ▼
┌───────────────┐
│   Starlette   │  ASGI framework underneath FastAPI. Routes requests.
│   (routing)   │
└───────┬───────┘
        │  Matches path → calls endpoint
        ▼
┌───────────────┐
│   FastAPI     │  Resolves Depends(), validates input, runs endpoint.
│   (endpoint)  │
└───────┬───────┘
        │  Your code
        ▼
┌───────────────┐
│  Your async   │  await get_patient(), await generate_briefing()
│  endpoint     │
└───────────────┘
```

### What Is ASGI?

**ASGI (Asynchronous Server Gateway Interface)** is the protocol between the server (uvicorn) and the application (FastAPI). It replaced WSGI (the synchronous protocol used by Flask/Django with gunicorn).

```python
# WSGI (synchronous):
def application(environ, start_response):
    # Must return response synchronously -- blocks the thread
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"Hello"]

# ASGI (asynchronous):
async def application(scope, receive, send):
    # Can await I/O -- suspends while waiting, event loop runs other requests
    await send({"type": "http.response.start", "status": 200, "headers": [...]})
    await send({"type": "http.response.body", "body": b"Hello"})
```

The key difference: ASGI is `async`. The application can `await` I/O operations without blocking the server. This is what makes FastAPI fundamentally different from Flask.

AI DOCTOR EXAMPLE:
In `main.py` lines 23-26, the `lifespan()` context manager is an ASGI lifespan handler. uvicorn calls it at startup (before `yield`) and shutdown (after `yield`). The `await engine.dispose()` on line 26 cleanly closes all PostgreSQL connections when the server shuts down -- an async operation managed by the ASGI lifecycle.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield                      # server is running, accepting requests
    await engine.dispose()     # server shutting down, close DB connections
```

---

## 2. `async def` vs `def` Endpoints

### Two Execution Models in One Framework

This is the **most important practical knowledge** in this document. FastAPI handles `async def` and `def` endpoints differently:

```python
# OPTION A: async def -- runs directly on the event loop
@router.post("/{patient_id}/briefing")
async def create_briefing(patient_id: int, session: AsyncSession = Depends(get_session)):
    patient = await get_patient_by_id(session, patient_id)  # suspends, loop free
    return await generate_briefing(patient)                  # suspends, loop free

# OPTION B: def -- runs in a threadpool (Starlette's anyio threadpool)
@router.get("/health")
def health_check():
    return {"status": "healthy"}  # sync, no I/O, thread is fine
```

### How Starlette Dispatches Them

```
Incoming HTTP request
        │
        ▼
┌───────────────────┐
│  Is endpoint       │
│  async def?        │
└────────┬──────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
   YES        NO
    │         │
    ▼         ▼
┌──────┐  ┌──────────────────┐
│ Run  │  │ Run in threadpool │
│ on   │  │ (Starlette wraps  │
│ event│  │  sync function in │
│ loop │  │  run_in_executor) │
└──────┘  └──────────────────┘
```

- **`async def`**: Starlette calls the coroutine directly on the event loop. If you do blocking I/O inside (like `requests.get()`), you freeze the loop.
- **`def`**: Starlette runs the function in a threadpool (via `anyio.to_thread.run_sync`). The event loop stays free. But you pay the thread overhead.

### When to Use Which

| Endpoint Type | Use `async def` | Use `def` |
|---------------|----------------|-----------|
| Calls async libraries (asyncpg, httpx, Agent SDK) | Yes | No |
| No I/O at all (health check, config) | Either works | Simpler |
| Calls sync-only libraries (no async version) | No (blocks loop!) | Yes (threadpool protects the loop) |
| Mixed: some async I/O, some sync I/O | Use `async def` + `run_in_executor()` for sync parts | No |

**Rule of thumb**: If any I/O in the endpoint is async (which it should be in a modern FastAPI app), use `async def`.

### The Dangerous Mistake

```python
# DANGEROUS: sync I/O inside async def
@router.post("/fetch-external")
async def fetch_external():
    response = requests.get("https://slow-api.com/data")  # blocks event loop!
    return response.json()

# The event loop is frozen for the entire duration of requests.get().
# All other requests stop being processed.
# This is worse than def because def would at least use the threadpool.
```

If you use `async def`, **every I/O call inside must be async** (using `await`). If you use `def`, sync I/O is fine because Starlette runs it in a threadpool.

AI DOCTOR EXAMPLE:
Every endpoint in the AI Doctor backend uses `async def` because every I/O call is async: `await get_patient_by_id()` (asyncpg), `await generate_briefing()` (Agent SDK). The `health_check()` in `main.py` line 49 is also `async def` -- this is fine because it has no I/O at all (just returns a dict).

---

## 3. Dependency Injection and Async

### How `Depends` Works With Async Generators

FastAPI's dependency injection resolves dependencies before calling your endpoint. Dependencies can be async:

```python
# database.py -- async generator dependency
async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
    # session is automatically closed here (after the endpoint returns)
```

```python
# briefings.py -- endpoint receives the dependency
@router.post("/{patient_id}/briefing")
async def create_briefing(
    patient_id: int,
    session: AsyncSession = Depends(get_session),  # ← injected by FastAPI
):
    patient = await get_patient_by_id(session, patient_id)
    ...
```

### The Lifecycle of a Dependency

```
Request arrives
      │
      ▼
┌─────────────────────────────────────────────────┐
│  FastAPI resolves Depends(get_session):          │
│                                                  │
│  1. Calls get_session() → async generator        │
│  2. Runs until yield → session is created        │
│  3. Injects session into the endpoint function   │
│                                                  │
│  ─── endpoint runs with session ───              │
│                                                  │
│  4. Endpoint returns (or raises)                 │
│  5. FastAPI resumes get_session() after yield    │
│  6. async with __aexit__ → session.close()       │
└─────────────────────────────────────────────────┘
```

The `yield` is the key. Everything before `yield` is setup (opening the session). Everything after `yield` is cleanup (closing the session). FastAPI guarantees cleanup runs even if the endpoint raises an exception.

AI DOCTOR EXAMPLE:
In `database.py` lines 13-16, `get_session()` is an async generator that opens a session via `async with async_session() as session` and yields it. When `briefings.py` line 23 declares `session: AsyncSession = Depends(get_session)`, FastAPI:
1. Calls `get_session()`, creating an async session
2. Injects it into `create_briefing()`
3. After the endpoint returns (or raises), closes the session via the `async with` cleanup

This pattern ensures database sessions are never leaked, even on errors.

---

## 4. SQLAlchemy Async

### Why `asyncpg` + `AsyncSession` + `create_async_engine`

The AI Doctor backend uses SQLAlchemy 2.0's async API:

```python
# database.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

This stack works as follows:

```
Your code                   SQLAlchemy                asyncpg              PostgreSQL
─────────                   ──────────                ───────              ──────────
await session.execute() ──→ Translates to SQL ──────→ Sends bytes ──────→ Processes query
                           (sync, ~microseconds)     (async, suspends)    (external, ~5ms)
                                                     ←── OS signals ←─── Returns rows
await resumes ←─────────── Wraps result ←─────────── Receives bytes
```

The important part: `asyncpg` (the PostgreSQL driver) is a **native async library**. When you `await session.execute()`, asyncpg sends the SQL query over the network and the coroutine **suspends**. The event loop is free to handle other requests during the database round-trip.

### Why `expire_on_commit=False`

```python
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

By default, SQLAlchemy expires all attributes on commit -- accessing `patient.name` after commit would trigger a **lazy load** (a new DB query). In async, lazy loads are dangerous because they happen implicitly (no `await`), which would block the event loop.

`expire_on_commit=False` tells SQLAlchemy: "after commit, keep the data in memory. Don't try to refresh from the database." This avoids accidental lazy loads in async code.

### Connection Pooling

`create_async_engine()` maintains an async **connection pool**:

```
┌──────────────────────────────────────────┐
│  AsyncEngine Connection Pool             │
│                                          │
│  ┌──────┐  ┌──────┐  ┌──────┐          │
│  │Conn 1│  │Conn 2│  │Conn 3│  ...      │
│  └──┬───┘  └──┬───┘  └──┬───┘          │
│     │         │         │                │
│  Request A  Request B  Request C         │
│                                          │
│  Default: pool_size=5, max_overflow=10   │
│  Max concurrent DB connections: 15       │
└──────────────────────────────────────────┘
```

Multiple coroutines can check out connections concurrently. When a coroutine `await`s a query, the connection is held but the coroutine is suspended -- the event loop serves other requests.

AI DOCTOR EXAMPLE:
In `patient_service.py` lines 13-15, `await session.execute(select(Patient).order_by(Patient.id))` checks out a connection from the pool, sends the query to PostgreSQL, suspends the coroutine, receives the result, and returns the connection to the pool. If 10 requests call this simultaneously, the pool serves them concurrently with 5 connections (others wait briefly for a free connection).

---

## 5. Concurrency Under Load

### Single Worker: Async I/O Concurrency

A single uvicorn worker (one process, one event loop, one thread) handles concurrent requests via async:

```
50 concurrent briefing requests on 1 uvicorn worker:

Event loop:
├── Coroutine 1:  [DB 5ms][────── Claude 5s ──────][return]
├── Coroutine 2:  [DB 5ms][────── Claude 5s ──────][return]
├── Coroutine 3:  [DB 5ms][────── Claude 5s ──────][return]
├── ...
└── Coroutine 50: [DB 5ms][────── Claude 5s ──────][return]

All 50 coroutines are suspended during their Claude API calls.
The event loop is idle during that time (good -- there is nothing to do).
All 50 responses come back within ~5-6 seconds.

Memory: 50 coroutines × ~2KB = ~100KB overhead
CPU: near zero (all waiting on network I/O)
```

### Multiple Workers: CPU Parallelism

```bash
# Multiple workers for multi-core utilization
uvicorn src.main:app --workers 4
```

Each worker is a **separate process** with its own event loop:

```
┌──────────────────────────────────────────────┐
│  uvicorn with 4 workers                      │
│                                              │
│  Worker 1 (Process, Event Loop):             │
│  └── handles ~25% of requests via async      │
│                                              │
│  Worker 2 (Process, Event Loop):             │
│  └── handles ~25% of requests via async      │
│                                              │
│  Worker 3 (Process, Event Loop):             │
│  └── handles ~25% of requests via async      │
│                                              │
│  Worker 4 (Process, Event Loop):             │
│  └── handles ~25% of requests via async      │
│                                              │
│  Each worker independently handles thousands │
│  of concurrent I/O operations.               │
│  4 workers = 4 CPU cores utilized.           │
└──────────────────────────────────────────────┘
```

### When Do You Need Multiple Workers?

| Scenario | 1 Worker | 4 Workers |
|----------|----------|-----------|
| I/O-bound (API calls, DB queries) | Handles thousands concurrently | Same, split across cores |
| CPU-bound (JSON serialization, validation) | Bottlenecked on 1 core | 4x throughput |
| Mixed (both I/O and CPU) | CPU part limits throughput | CPU part scales with workers |

For the AI Doctor, the workload is overwhelmingly I/O-bound (waiting on Claude, PostgreSQL, Qdrant). A single async worker can handle hundreds of concurrent requests. Multiple workers help if:
- You have CPU-heavy work (document parsing during ingestion)
- You want fault isolation (one worker crashing doesn't kill all requests)
- You are running in Kubernetes and want to utilize all allocated CPU cores

---

## 6. The Claude Agent SDK `async for` Pattern

### How `query()` Works as an Async Iterator

The Claude Agent SDK's `query()` function returns an **async iterator** -- not a single result. This is different from a regular `await`:

```python
# Regular await: one request, one response
patient = await get_patient_by_id(session, 1)

# Async iterator: one request, multiple yielded messages
async for message in query(prompt=patient_json, options=options):
    if isinstance(message, ResultMessage):
        result = message.structured_output
```

### Why It's an Async Iterator

The Claude Agent SDK processes the agent's response as a **stream of messages**. In a multi-turn agent with tools, the sequence is:

```
query(prompt, options)
    │
    ├── yield AssistantMessage (agent thinking)
    ├── yield ToolCallMessage (agent calls a tool)
    ├── yield ToolResultMessage (tool returns result)
    ├── yield AssistantMessage (agent thinking again)
    └── yield ResultMessage (final structured output)
```

Each `yield` is a suspension point. Between yields, the coroutine is suspended and the event loop handles other requests.

### Tracing Through `briefing_service.py`

```python
# briefing_service.py lines 108-115
async for message in query(prompt=patient_json, options=options):
    if isinstance(message, ResultMessage):
        if not message.is_error and message.structured_output is not None:
            briefing = PatientBriefing.model_validate(message.structured_output)
            result = BriefingResponse(
                **briefing.model_dump(),
                generated_at=datetime.datetime.now(datetime.UTC),
            )
```

The execution timeline:

```
async for message in query(...):
      │
      ├── SDK sends prompt to Claude ──── SUSPEND (waiting for Claude)
      │   [event loop serves other requests]
      │
      ├── Claude responds with AssistantMessage
      │   [loop body runs: isinstance check, not ResultMessage, continue]
      │
      ├── Claude calls tool ──── SUSPEND (tool execution)
      │   [event loop serves other requests]
      │
      ├── Tool result returns, Claude continues
      │   [loop body runs: isinstance check, not ResultMessage, continue]
      │
      ├── Claude responds with ResultMessage
      │   [loop body runs: isinstance check → YES]
      │   [model_validate, build BriefingResponse]
      │
      └── Iteration ends
```

AI DOCTOR EXAMPLE:
With RAG (multi-turn), the `query()` call in `briefing_service.py` may yield 5-7 messages over 8-10 seconds (think → search tool → result → think → search again → result → final output). During each suspension between messages, the event loop handles other requests. A single uvicorn worker can process multiple patients' briefings concurrently, each at different stages of the agent loop.

---

## 7. Summary

```
FASTAPI ASYNC ARCHITECTURE:

1. uvicorn creates the event loop and owns the server socket
2. ASGI connects uvicorn to FastAPI (async protocol)
3. async def endpoints run on the event loop (must never block)
4. def endpoints run in a threadpool (safe for sync I/O)
5. Depends() resolves async generators, manages lifecycle
6. SQLAlchemy async uses asyncpg for non-blocking DB queries
7. Connection pools serve multiple coroutines concurrently
8. Multiple uvicorn workers add CPU parallelism across cores
9. query() returns an async iterator for streaming agent messages
```

| Component | Role | Key Detail |
|-----------|------|-----------|
| **uvicorn** | Event loop owner, HTTP server | Creates loop, parses HTTP, calls ASGI app |
| **ASGI** | Protocol between server and app | Async version of WSGI |
| **Starlette** | Routing, middleware, `async def`/`def` dispatch | Runs `def` endpoints in threadpool |
| **FastAPI** | Dependency injection, validation, serialization | `Depends()` resolves async generators |
| **SQLAlchemy async** | Non-blocking DB access | `create_async_engine` + `AsyncSession` + asyncpg |
| **Claude Agent SDK** | Async iterator for agent messages | `async for message in query(...)` |

---

**Next**: `04-ASYNC-PATTERNS-FOR-RAG.md` -- Applying async patterns to the RAG pipeline: async Qdrant, parallel embeddings, agent tool loops, and common antipatterns.
