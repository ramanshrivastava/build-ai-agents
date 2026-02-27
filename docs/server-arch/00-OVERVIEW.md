# Async Server Architecture

**Series Overview**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [What This Documentation Is For](#what-this-documentation-is-for)
2. [Prerequisites](#prerequisites)
3. [Recommended Reading Order](#recommended-reading-order)
4. [Suggested Paths](#suggested-paths)
5. [Conventions Used](#conventions-used)
6. [How to Use This Series](#how-to-use-this-series)
7. [What This Series Does NOT Cover](#what-this-series-does-not-cover)
8. [Cross-References](#cross-references)
9. [Document Maintenance](#document-maintenance)

---

## What This Documentation Is For

This is an educational series about async/await, event loops, and concurrent I/O design for Python web servers.

These documents are written for developers who:

- Build with FastAPI and want to understand what `async def` and `await` actually do at runtime
- Need to design endpoints that call multiple external services (databases, vector DBs, LLM APIs) efficiently
- Are curious about how Python's event loop works -- not just the syntax, but the execution model
- Want to reason about concurrency in a RAG pipeline where a single request chains 3-5 I/O operations

**This is not a quickstart.** It prioritizes depth over speed. Each document explains *why* before *how*, building mental models that transfer beyond FastAPI to any async Python system.

---

## Prerequisites

Before reading this series, you should have:

- **Basic Python**: Can read code, write functions, understand classes and generators
- **HTTP/REST Concepts**: Understand request/response cycle, status codes, JSON payloads
- **FastAPI Awareness**: Have seen a FastAPI endpoint definition (even if you don't know the internals)
- **The AI Doctor Codebase**: Familiarity with the project structure from `docs/ARCHITECTURE.md`

You do **not** need:

- Prior experience with `asyncio` -- Document 01 starts from the synchronous world
- Understanding of OS-level I/O multiplexing (epoll, kqueue) -- we stay at the Python level
- Knowledge of threading or multiprocessing -- we compare against threads but don't require thread expertise
- Experience with other async frameworks (Node.js, Go goroutines) -- all concepts are Python-first

---

## Recommended Reading Order

| Document | Title | Description |
|----------|-------|-------------|
| **00-OVERVIEW.md** | This overview | Series structure, prerequisites, conventions |
| **01-SYNC-VS-ASYNC.md** | Synchronous vs Asynchronous I/O | The problem: blocking I/O, thread costs, why async exists |
| **02-EVENT-LOOP-AND-COROUTINES.md** | Python's Event Loop and Coroutines | The mechanism: coroutines, `await`, event loop, `asyncio.gather()` |
| **03-FASTAPI-ASYNC-ARCHITECTURE.md** | FastAPI's Async Architecture | The framework: uvicorn, ASGI, async endpoints, SQLAlchemy async |
| **04-ASYNC-PATTERNS-FOR-RAG.md** | Async Patterns for RAG Pipelines | The application: async Qdrant, embeddings, agent loops, antipatterns |

---

## Suggested Paths

### Builders Path (Skip the Internals)

**Goal**: Write correct async FastAPI endpoints without deep event loop knowledge.

```
00 → 01 → 03 → 04
│    │    │    │
│    │    │    └─ RAG patterns: Design async endpoints for embed + search + LLM
│    │    └─ FastAPI: async def vs def, dependencies, SQLAlchemy async
│    └─ Why async: The blocking problem, when async helps
└─ This overview
```

**Time estimate**: 3-4 hours. You skip the event loop deep-dive (Doc 02) and go straight to practical patterns.

### Understanding Path (Full Sequential)

**Goal**: Understand what happens inside Python when you write `await`, from coroutines to the event loop to ASGI.

```
00 → 01 → 02 → 03 → 04
│    │    │    │    │
│    │    │    │    └─ RAG: Apply everything to the ingestion + retrieval pipeline
│    │    │    └─ FastAPI: How uvicorn, ASGI, and async endpoints connect
│    │    └─ Event loop: Coroutines, await mechanics, gather, create_task
│    └─ Why async: Blocking I/O, threads, the event loop alternative
└─ This overview
```

**Time estimate**: 5-7 hours. Read in order -- each document builds on the previous.

### "Fix My Slow Endpoint" Path

**Goal**: Diagnose and fix async performance issues in an existing FastAPI + RAG system.

```
00 → 03 → 04
│    │    │
│    │    └─ RAG: Dependency graphs, gather(), antipatterns, profiling
│    └─ FastAPI: async def gotchas, blocking footguns, threadpool behavior
└─ This overview
```

**Time estimate**: 2-3 hours. Jump to the practical docs. Refer back to 01-02 when you need the "why."

---

## Conventions Used

### Formatting

**Code Blocks**: Python code, shell commands, and configuration appear in fenced code blocks with language hints:

```python
# Example: An async FastAPI endpoint
@router.post("/{patient_id}/briefing")
async def create_briefing(
    patient_id: int,
    session: AsyncSession = Depends(get_session),
) -> BriefingResponse:
    patient = await get_patient_by_id(session, patient_id)
    return await generate_briefing(patient)
```

```bash
# Example: Starting the async server
cd backend && uv run uvicorn src.main:app --reload
```

**Inline Code**: Commands, file paths, API fields, and technical terms appear in `backticks` (e.g., `async def`, `src/database.py`, `asyncio.gather()`).

**Tables**: Used for comparisons (sync vs async, thread vs coroutine), parameter references, and structured lists.

**ASCII Diagrams**: Timeline visualizations, execution flow diagrams, and architecture overviews use text-based diagrams.

**Mermaid Diagrams**: Sequence diagrams and complex flowcharts use fenced `mermaid` code blocks. See [`docs/tooling/MERMAID-CHEATSHEET.md`](../tooling/MERMAID-CHEATSHEET.md) for syntax reference.

### AI Doctor Callouts

Examples specific to the AI Doctor Assistant app use this format:

```
AI DOCTOR EXAMPLE:
When a briefing request arrives, the endpoint awaits get_patient_by_id()
(PostgreSQL query via asyncpg), then awaits generate_briefing() which
internally awaits the Claude Agent SDK query(). Each await suspends the
coroutine and frees the event loop to handle other requests.
```

These ground abstract concepts in the actual application.

### Emphasis Patterns

- **Bold**: Key terms on first mention, important warnings, critical concepts
- *Italics*: Emphasis within explanations, contrasts, nuance
- ALL CAPS: Reserved for acronyms (ASGI, WSGI, GIL) and environment variables (DATABASE_URL)

---

## How to Use This Series

### For Learning

1. **Read 01** to understand why synchronous servers struggle with I/O-heavy workloads like RAG.
2. **Read 02** to understand the mechanics -- what a coroutine is, what `await` does, how the event loop schedules work.
3. **Read 03** to see how FastAPI, uvicorn, and SQLAlchemy connect these concepts into a working server.
4. **Read 04** to design async endpoints for the RAG pipeline -- embedding, vector search, agent loops.

### For Building

1. Start with **01** to understand when async helps and when it doesn't.
2. Jump to **03** for FastAPI-specific patterns (`async def` vs `def`, dependency injection, connection pools).
3. Read **04** before implementing RAG endpoints -- it covers the Qdrant async client, `asyncio.gather()` for parallel searches, and common antipatterns.

### For Debugging

1. Read **03** Section 2 (`async def` vs `def`) -- the most common source of async bugs in FastAPI.
2. Read **04** Section 7 (Async Antipatterns) -- a table of mistakes and their fixes.
3. Refer to **02** when you need to understand *why* something is blocking the event loop.

### For Reference

- **01**: Thread memory costs, I/O-bound vs CPU-bound table, when async helps
- **02**: `await` mechanics, `gather()` vs `create_task()` vs `await`, event loop pseudocode
- **03**: ASGI lifecycle, `async def` vs `def` dispatch, SQLAlchemy async session patterns
- **04**: RAG I/O chain diagram, async Qdrant client setup, antipattern table

---

## What This Series Does NOT Cover

- **Threading and multiprocessing in depth**: We compare threads to async for motivation but don't teach `threading` or `multiprocessing` modules. See Python docs for those.
- **OS-level I/O multiplexing**: `epoll`, `kqueue`, `select` are mentioned conceptually but not explored. This series stays at the Python level.
- **JavaScript async / Node.js**: Concepts transfer, but all code is Python. We don't compare event loop implementations across languages.
- **Advanced asyncio internals**: Event loop policies, custom event loops, `asyncio.Protocol`, low-level transport/protocol APIs. We cover what application developers need, not asyncio library developers.
- **Async testing patterns**: Testing is covered in the context of specific documents (e.g., profiling in Doc 04) but is not a standalone topic. See `docs/RAG-ARCH.md` Section 9 for the RAG testing strategy.

---

## Cross-References

This series connects to the **Agent Architecture Series** (`docs/agent-arch/`) and **RAG Architecture** (`docs/RAG-ARCH.md`):

- **`agent-arch/01-ANTHROPIC-API-FUNDAMENTALS.md`**: The stateless API model (each call is independent I/O) is the foundation for understanding why async matters -- each API call is an I/O wait. Read after `01-SYNC-VS-ASYNC.md`.
- **`agent-arch/07-CLAUDE-AGENT-SDK.md`**: The `query()` function returns an async generator (`async for message in query(...)`). The event loop mechanics from `02-EVENT-LOOP-AND-COROUTINES.md` explain how this works.
- **`infra-arch/05-APP-ON-K8S.md`**: uvicorn workers map to Pod resource requests in Kubernetes. Understanding async concurrency (Doc 03) helps you right-size your Pod CPU/memory.
- **`RAG-ARCH.md`**: The entire RAG pipeline that `04-ASYNC-PATTERNS-FOR-RAG.md` teaches you to build with async. Contains the architecture diagrams, tool definitions, and data models.

---

## Document Maintenance

These documents reflect:

- **Python**: 3.12 (asyncio stable API)
- **FastAPI**: 0.100+ (Starlette 0.27+ ASGI lifecycle)
- **uvicorn**: 0.24+ (uvloop event loop on Linux/macOS)
- **SQLAlchemy**: 2.0 async API (`create_async_engine`, `AsyncSession`)
- **Qdrant**: Python client 1.12+ (`AsyncQdrantClient`)
- **AI Doctor**: V1 complete (FastAPI + React 19 + PostgreSQL), RAG iteration in progress

The async patterns in Python's `asyncio` module are stable and unlikely to change significantly across Python 3.12+. FastAPI's async behavior has been stable since Starlette adopted the ASGI lifespan protocol. Document updates will primarily be needed when the AI Doctor codebase evolves (new services, new external API integrations).

---

**Next Steps**: Proceed to `01-SYNC-VS-ASYNC.md` to understand why synchronous servers struggle with I/O-heavy workloads, or jump to `03-FASTAPI-ASYNC-ARCHITECTURE.md` if you already understand async fundamentals and want to see how FastAPI uses them.
