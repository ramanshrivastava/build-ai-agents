# Synchronous vs Asynchronous I/O

**Part 1 of 5: Async Server Architecture Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Learning Objectives](#learning-objectives)
2. [The Blocking Problem](#1-the-blocking-problem)
3. [I/O-Bound vs CPU-Bound](#2-io-bound-vs-cpu-bound)
4. [The Thread-Per-Request Model](#3-the-thread-per-request-model)
5. [The Event Loop Alternative](#4-the-event-loop-alternative)
6. [Where Async Matters in Our Stack](#5-where-async-matters-in-our-stack)
7. [Summary](#6-summary)

---

## Learning Objectives

After reading this document, you will understand:

- Why a synchronous web server **blocks** on I/O and what that means for concurrent users
- The difference between **I/O-bound** and **CPU-bound** work, and why this distinction determines whether async helps
- How the **thread-per-request** model works, its memory costs, and where it breaks down
- What **non-blocking I/O** means at a conceptual level -- the event loop alternative to threads
- Why async became the **dominant model** for Python web servers that call external APIs

Key mental models to internalize:

- **"Waiting is not working."** A thread blocked on a network response consumes resources while producing nothing. The entire point of async is to reclaim that wasted time.
- **"I/O-bound vs CPU-bound is THE question."** Async helps the first, not the second. Every design decision starts here.
- **Async is about concurrency, not speed.** A single request doesn't get faster. The server handles *more* requests simultaneously.

Common misconceptions to avoid:

- "Async makes my code faster" -- No. It makes I/O *waiting* more efficient. A single database query takes the same time sync or async.
- "I need async for everything" -- No. If your endpoint does pure computation with no I/O, async adds complexity for no benefit.
- "Threads solve concurrency" -- They do, but at a cost (memory per thread, GIL contention, context switching). Async solves I/O concurrency without those costs.
- "Async means parallel" -- No. Async is *concurrent* (interleaved on one thread), not *parallel* (simultaneous on multiple cores). True parallelism requires multiprocessing.

---

## 1. The Blocking Problem

### What Happens When Your Server Waits

Consider the AI Doctor briefing endpoint. A single `POST /api/v1/patients/1/briefing` request does the following:

```
┌────────────────────────────────────────────────────────────────────┐
│  A single briefing request (V1, no RAG):                           │
│                                                                    │
│  [Parse request]                                          ~1ms     │
│  [await get_patient_by_id(session, patient_id)] ─── DB    ~5ms     │
│  [await generate_briefing(patient)]                                │
│     └── [async for message in query(prompt, options)]              │
│            └── Claude Agent SDK call ──────────────── LLM  ~3-8s   │
│  [Serialize response]                                     ~1ms     │
│                                                                    │
│  Total: ~3-8 seconds                                               │
│  Time doing actual work: ~2ms                                      │
│  Time WAITING for I/O: ~3-8 seconds (99.97% of the time!)         │
└────────────────────────────────────────────────────────────────────┘
```

The server spends **99.97%** of the request duration doing nothing -- just waiting for bytes to come back over the network.

### What This Looks Like With a Synchronous Server

In a synchronous server (like Flask with a sync WSGI worker), each request occupies a thread for its entire lifetime:

```
Sync server: 3 users request briefings at the same time

Thread 1: [Parse]──[DB 5ms]──[────── Claude API 5 seconds ──────]──[Return]
                                                                        ↑ User 1 done

Thread 2:          [Parse]──[DB 5ms]──[────── Claude API 5 seconds ──────]──[Return]
                                                                                ↑ User 2 done

Thread 3:                    [Parse]──[DB 5ms]──[────── Claude API 5 seconds ──────]──[Return]
                                                                                          ↑ User 3 done

█ = doing work    ─ = waiting (thread blocked, consuming memory, doing nothing)
```

Each thread sits idle for ~5 seconds. During that time, the thread:
- Consumes ~8MB of stack memory
- Holds an OS-level resource (thread handle)
- Cannot serve any other request
- Is literally doing nothing

If a 4th user arrives and you only have 3 threads, they **wait in a queue** until a thread frees up.

AI DOCTOR EXAMPLE:
The current `briefings.py` endpoint calls `await get_patient_by_id(session, patient_id)` (line 25) then `await generate_briefing(patient)` (line 37). The `generate_briefing()` function internally iterates `async for message in query(prompt, options)` which waits for the Claude Agent SDK to return. In a sync server, the thread handling this request would be blocked for the entire 3-8 second duration of the Claude API call. With 4 gunicorn sync workers, only 4 briefings can be generated simultaneously -- user 5 waits.

---

## 2. I/O-Bound vs CPU-Bound

### The Fundamental Distinction

Every operation your server performs falls into one of two categories:

| Type | What It Does | Where Time Goes | Example |
|------|-------------|----------------|---------|
| **I/O-bound** | Waits for data from an external system | Network, disk, or device latency | Database query, API call, file read |
| **CPU-bound** | Computes a result using the processor | CPU cycles | JSON parsing, sorting, hashing, math |

**Async helps I/O-bound work.** When a coroutine hits `await` on an I/O operation, it suspends and the event loop runs other coroutines. The I/O completes in the background (handled by the OS) and the coroutine resumes with the result.

**Async does NOT help CPU-bound work.** If your code is crunching numbers, there is no I/O to wait for. The CPU is already fully utilized. `await` has nothing to "yield to" because there is no idle time to reclaim.

### The AI Doctor Stack Mapped

| Operation | Type | Latency | Where It Happens |
|-----------|------|---------|-----------------|
| `await session.execute(select(Patient))` | **I/O** | ~5ms | PostgreSQL via asyncpg |
| `await embed_text(query)` | **I/O** | ~50-200ms | Vertex AI API (network) |
| `await qdrant_client.search(...)` | **I/O** | ~10-50ms | Qdrant (network/gRPC) |
| `async for message in query(prompt, options)` | **I/O** | ~3-8s | Claude API via Agent SDK |
| `PatientBriefing.model_validate(data)` | **CPU** | <1ms | Pydantic validation (local) |
| `json.dumps(result.model_dump())` | **CPU** | <1ms | JSON serialization (local) |
| `_serialize_patient(patient)` | **CPU** | <1ms | Dict construction + json.dumps |

**The ratio is overwhelming.** The I/O operations take seconds. The CPU operations take microseconds. This is a textbook I/O-bound workload. Async is the right model.

### Why Python's GIL Makes This Even More Important

Python has a **Global Interpreter Lock (GIL)** -- only one thread can execute Python bytecode at a time. This means:

- **Threads don't give you CPU parallelism in Python.** Two threads crunching numbers take the same time as one thread (GIL serializes them).
- **Threads DO help with I/O** because the GIL is released during I/O operations (the OS handles the I/O, not the Python interpreter).
- **Async is equally effective for I/O and doesn't need the GIL at all** -- there is only one thread, so no contention.

```
Threads + GIL (Python):

Thread A: [Python code]──[RELEASE GIL: I/O wait]──[Python code]
Thread B:                 [Python code]────────────[RELEASE GIL: I/O wait]──[Python code]
                          ↑                        ↑
                     Only one thread              GIL bounces
                     runs Python at a time        between threads

Async (no GIL issue):

Coroutine A: [Python code]──[await: suspend]──────────[Python code]
Coroutine B:                 [Python code]──[await: suspend]──[Python code]
                             ↑
                        One thread, no GIL contention.
                        Coroutines yield voluntarily.
```

For an I/O-bound web server, async avoids the GIL overhead entirely while achieving the same concurrent I/O as threads.

---

## 3. The Thread-Per-Request Model

### How Traditional Sync Servers Work

A synchronous WSGI server (like gunicorn with sync workers, or Flask's built-in server) uses a **thread pool** to handle requests:

```
┌──────────────────────────────────────────────────────────┐
│  WSGI Server (gunicorn --workers 4 --threads 4)          │
│                                                          │
│  Worker Process 1 (4 threads):                           │
│  ├── Thread A: [handling request] or [idle]              │
│  ├── Thread B: [handling request] or [idle]              │
│  ├── Thread C: [handling request] or [idle]              │
│  └── Thread D: [handling request] or [idle]              │
│                                                          │
│  Worker Process 2 (4 threads):                           │
│  ├── Thread E: ...                                       │
│  └── ...                                                 │
│                                                          │
│  Total concurrent requests: 4 workers × 4 threads = 16  │
│  Memory: 4 workers × ~150MB = ~600MB base               │
│         + 16 threads × ~8MB stack = ~128MB               │
│  Total: ~728MB for 16 concurrent requests                │
└──────────────────────────────────────────────────────────┘
```

### The Cost of Threads

| Resource | Per Thread | 100 Threads | 1000 Threads |
|----------|-----------|-------------|--------------|
| Stack memory | ~8MB (default) | ~800MB | ~8GB |
| OS thread handle | 1 | 100 | 1000 (may hit ulimit) |
| Context switch cost | ~1-10 microseconds | Frequent | Constant |
| GIL contention | N/A | Moderate | Severe |

For the AI Doctor use case, each thread is blocked for 3-8 seconds (waiting for Claude). To handle 100 concurrent briefing requests, you need 100 threads -- consuming ~800MB just for stacks. And they are all idle, waiting for API responses.

### Where Threads Break Down

1. **Memory ceiling.** At ~8MB per thread, 1000 concurrent connections = 8GB just for thread stacks. The server runs out of memory before it runs out of CPU.

2. **Context switching overhead.** The OS scheduler switches between 100+ threads even though they are all just waiting. Each context switch has a small cost that adds up.

3. **GIL contention.** When threads wake up to process responses, they compete for the GIL. With many threads, GIL acquisition becomes a bottleneck.

4. **Thread pool exhaustion.** If all threads are blocked on slow Claude API calls, new requests queue. The server appears unresponsive even though it has spare CPU.

AI DOCTOR EXAMPLE:
A clinic has 20 doctors using the system during morning rounds, all requesting briefings within a few minutes. Each briefing ties up a thread for ~5 seconds. With gunicorn running 4 workers × 4 threads = 16 concurrent slots, doctors 17-20 wait in a queue. With async, all 20 requests are processed concurrently on a single worker.

---

## 4. The Event Loop Alternative

### The Core Idea: Don't Block. Suspend.

Instead of one thread per request, async uses **one thread** with **many coroutines**. When a coroutine would block on I/O, it **suspends** (yields control) and the event loop runs another coroutine:

```
┌──────────────────────────────────────────────────────────┐
│  Async Server (uvicorn, single worker):                  │
│                                                          │
│  Event Loop (1 thread):                                  │
│  ├── Coroutine A: briefing for patient 1 (awaiting DB)   │
│  ├── Coroutine B: briefing for patient 2 (awaiting LLM)  │
│  ├── Coroutine C: briefing for patient 3 (awaiting LLM)  │
│  ├── Coroutine D: patient list query (awaiting DB)       │
│  └── Coroutine E: health check (ready to return)         │
│                                                          │
│  Memory per coroutine: ~1-2KB (vs ~8MB per thread)       │
│  Concurrent requests: thousands                          │
│  CPU: near zero (all waiting on I/O)                     │
└──────────────────────────────────────────────────────────┘
```

### How It Handles 3 Concurrent Briefing Requests

```
Async event loop with 3 concurrent briefing requests:

Time ──────────────────────────────────────────────────────────►

Loop: [Parse A][DB A, suspend A]
      [Parse B][DB B, suspend B]
      [Parse C][DB C, suspend C]
      ─── idle (OS handles all 3 DB queries) ───
      [Resume A: DB done][Call Claude A, suspend A]
      [Resume B: DB done][Call Claude B, suspend B]
      [Resume C: DB done][Call Claude C, suspend C]
      ─── idle (OS handles all 3 API calls) ───
      [Resume A: Claude done][Serialize][Return A]
      [Resume B: Claude done][Serialize][Return B]
      [Resume C: Claude done][Serialize][Return C]

Total time: ~5 seconds (bounded by the slowest Claude call)
Threads used: 1
Memory overhead: ~6KB (3 coroutines × ~2KB)
```

Compare to the sync model where 3 threads use ~24MB and all sit idle for 5 seconds.

### The Memory Advantage

```
100 concurrent briefing requests:

Sync (threads):   100 threads × 8MB  = 800MB memory
Async (coroutines): 100 coroutines × 2KB = 200KB memory

Factor: ~4000x less memory per concurrent connection.
```

This is why async servers like uvicorn can handle 10,000+ concurrent connections on modest hardware, while thread-based servers hit limits at hundreds.

### What the Event Loop Actually Does (Conceptual)

```python
# Simplified pseudocode -- this is what asyncio does internally:

ready_to_run = []
waiting_for_io = {}

while True:
    # 1. Ask the OS: "Did any I/O operations complete?"
    completed = os_poll(waiting_for_io)  # epoll (Linux), kqueue (macOS)

    # 2. Move completed coroutines to the ready queue
    for handle, coroutine in completed:
        ready_to_run.append(coroutine)

    # 3. Run each ready coroutine until it hits the next await
    for coroutine in ready_to_run:
        result = coroutine.resume()

        if result.needs_io:
            # Coroutine hit an await -- register with OS and move on
            waiting_for_io[result.io_handle] = coroutine
        elif result.done:
            # Coroutine finished -- send the HTTP response
            send_response(result.value)
```

The loop never blocks. It either runs coroutines or polls the OS for I/O completion. This is explored in depth in `02-EVENT-LOOP-AND-COROUTINES.md`.

---

## 5. Where Async Matters in Our Stack

### Single Request: Async Doesn't Help Latency

For a single isolated request, async and sync produce the same end-to-end latency:

```
Single request:

Sync:   [Parse]──[DB 5ms wait]──[Claude 5s wait]──[Return]    Total: ~5s
Async:  [Parse]──[await DB 5ms]──[await Claude 5s]──[Return]  Total: ~5s

Same! No speedup for one request alone.
```

Async doesn't make I/O faster. The database query takes the same time. The Claude API call takes the same time. The difference is what happens to the **server** while it waits.

### Multiple Concurrent Requests: Async Wins

When multiple requests arrive simultaneously, async handles them all on one thread without blocking:

| Scenario | Sync (4 threads) | Async (1 thread) |
|----------|-----------------|-------------------|
| 4 concurrent briefings | All 4 handled, 5s each | All 4 handled, 5s each |
| 10 concurrent briefings | 4 active, 6 queued (up to 15s wait) | All 10 handled, 5s each |
| 50 concurrent briefings | 4 active, 46 queued (60s+ wait) | All 50 handled, 5s each |
| 100 concurrent briefings | Thread pool exhausted | All 100 handled, ~5-6s each |

### Parallel I/O Within One Request: Async Wins (with `gather`)

With RAG, a single request makes **multiple independent I/O calls**. Async lets you overlap them:

```python
# SEQUENTIAL (one after another):
patient = await get_patient(session, id)       # 5ms
embeddings = await embed_text(query)           # 200ms
chunks = await qdrant.search(embeddings)       # 50ms
guidelines = await qdrant.search(embeddings2)  # 50ms
# Total I/O wait: 305ms

# CONCURRENT (independent calls in parallel):
patient = await get_patient(session, id)       # 5ms (must happen first)
embeddings = await embed_text(query)           # 200ms (must happen before search)

# These two searches are independent -- run them in parallel!
chunks, guidelines = await asyncio.gather(
    qdrant.search(embeddings),                 # 50ms ┐
    qdrant.search(embeddings2),                # 50ms ┘ overlapped = 50ms total
)
# Total I/O wait: 255ms (saved 50ms)
```

This is covered in depth in `04-ASYNC-PATTERNS-FOR-RAG.md`.

### When Async Does NOT Help

| Scenario | Why Async Doesn't Help |
|----------|----------------------|
| CPU-heavy computation | No I/O to yield during. CPU is the bottleneck, not waiting. |
| Single request, single I/O call | Nothing else to do while waiting. |
| Very low traffic (1-2 concurrent users) | Thread overhead is negligible at this scale. |
| Blocking library with no async support | If the library blocks the thread, async can't help. Use `run_in_executor()` as escape hatch. |

---

## 6. Summary

```
THE CORE ARGUMENT FOR ASYNC IN THE AI DOCTOR BACKEND:

1. Each briefing request waits 3-8 seconds for external APIs (I/O-bound)
2. A sync server blocks a thread per request during that wait
3. Threads cost ~8MB each and are limited by OS resources
4. Async uses coroutines (~2KB each) that suspend during I/O
5. The event loop runs other coroutines during the wait
6. Result: one thread handles thousands of concurrent requests

For a server that calls PostgreSQL, Qdrant, Vertex AI, and Claude:
→ 99.97% of request time is I/O waiting
→ Async is the right model
```

| Concept | Sync (Threaded) | Async (Event Loop) |
|---------|----------------|-------------------|
| Concurrency unit | Thread (~8MB) | Coroutine (~2KB) |
| During I/O wait | Thread blocked, idle | Coroutine suspended, loop runs others |
| 100 concurrent users | 100 threads, ~800MB | 100 coroutines, ~200KB |
| GIL contention | Yes (threads compete) | No (one thread) |
| CPU-bound work | Threads help (release GIL in C extensions) | Does not help (blocks the loop) |
| Complexity | Simple mental model | Must understand await/suspend |
| Python ecosystem | Flask, Django (traditional) | FastAPI, Starlette, aiohttp |

---

**Next**: `02-EVENT-LOOP-AND-COROUTINES.md` -- How `async def`, `await`, and the event loop actually work in Python.
