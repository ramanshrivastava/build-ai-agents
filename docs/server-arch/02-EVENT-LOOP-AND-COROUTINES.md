# Python's Event Loop and Coroutines

**Part 2 of 5: Async Server Architecture Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Learning Objectives](#learning-objectives)
2. [What Is a Coroutine?](#1-what-is-a-coroutine)
3. [What `await` Does](#2-what-await-does)
4. [The Event Loop](#3-the-event-loop)
5. [`asyncio.gather()` -- Concurrent I/O](#4-asynciogather----concurrent-io)
6. [`asyncio.run()` vs `await` vs `create_task()` vs `gather()`](#5-asynciorun-vs-await-vs-create_task-vs-gather)
7. [Common Pitfalls](#6-common-pitfalls)
8. [Summary](#7-summary)

---

## Learning Objectives

After reading this document, you will understand:

- What a **coroutine** is at the Python level -- a function that can be suspended and resumed
- What `await` does **mechanically** -- suspend this coroutine, return control to the event loop, resume when I/O completes
- How the **event loop** schedules coroutines and what "cooperative multitasking" means
- Why `asyncio.gather()` enables **concurrent I/O** within a single request
- When to use `asyncio.run()` (scripts) vs `await` (inside async functions) vs `asyncio.gather()` (parallel I/O)
- The **blocking footguns** that silently break async performance

Key mental models to internalize:

- A coroutine is a **pausable function**. `await` is the pause button. The event loop is the scheduler that decides what runs while something is paused.
- `asyncio.gather()` means "start all these coroutines, let them all wait on I/O concurrently, collect all results when done."
- The event loop is **not magic**. It is a `while True` loop that checks which I/O operations have completed and resumes the corresponding coroutines.

Common misconceptions to avoid:

- "`await` makes something run in the background" -- No. `await` *suspends the current coroutine* and gives control back to the event loop. The I/O itself is handled by the OS, not a background thread.
- "Coroutines run in parallel on multiple cores" -- No. They are concurrent on one thread. True parallelism requires `multiprocessing` or multiple uvicorn workers.
- "I need to create the event loop myself" -- No. In FastAPI, uvicorn creates it. Your endpoint functions are already running inside it. `asyncio.run()` is only for standalone scripts.
- "`await asyncio.sleep(5)` is the same as `time.sleep(5)`" -- No. `asyncio.sleep` suspends the coroutine (event loop runs others). `time.sleep` blocks the entire thread (event loop frozen).

---

## 1. What Is a Coroutine?

### `async def` Creates a Coroutine Function

A regular function runs to completion when called. A coroutine function can be **suspended** and **resumed**:

```python
# Regular function -- runs to completion, returns result immediately
def get_patient_sync(patient_id: int) -> Patient:
    result = db.execute(query)    # blocks until DB responds
    return result.scalar()        # runs immediately after

# Coroutine function -- CAN be suspended at await points
async def get_patient_async(session: AsyncSession, patient_id: int) -> Patient:
    result = await session.execute(query)   # SUSPENDS here. Resumes when DB responds.
    return result.scalar_one_or_none()      # Runs after resumption.
```

### Calling a Coroutine Function Returns a Coroutine Object

This is a common source of confusion. Calling `async def` does NOT execute the function:

```python
# This does NOT execute the function. It creates a coroutine object.
coro = get_patient_async(session, 1)
print(type(coro))  # <class 'coroutine'>

# To actually RUN it, you must await it (or pass it to the event loop):
patient = await get_patient_async(session, 1)  # NOW it executes
```

Think of a coroutine as a **recipe** -- it describes the steps but doesn't execute them. The event loop is the **chef** who follows the recipe and can pause one recipe to work on another.

### Under the Hood: Coroutines Are State Machines

When Python compiles `async def`, it creates a state machine. Each `await` is a **suspension point** that divides the function into segments:

```python
async def create_briefing(patient_id: int, session: AsyncSession):
    # ── Segment 1: Before first await ──
    patient = await get_patient_by_id(session, patient_id)  # Suspension point 1

    # ── Segment 2: After first await, before second ──
    result = await generate_briefing(patient)                # Suspension point 2

    # ── Segment 3: After second await ──
    return result
```

The event loop runs Segment 1, hits the await, suspends the coroutine, does other work, then comes back and runs Segment 2, suspends again, does other work, then runs Segment 3.

```
State machine view:

                  ┌─────────────┐
                  │  Segment 1  │  Parse request, prepare query
                  └──────┬──────┘
                         │ await (suspend → event loop)
                         ▼
              ─── other coroutines run ───
                         │
                         ▼ (DB responds, resume)
                  ┌─────────────┐
                  │  Segment 2  │  Build prompt, call agent
                  └──────┬──────┘
                         │ await (suspend → event loop)
                         ▼
              ─── other coroutines run ───
                         │
                         ▼ (Claude responds, resume)
                  ┌─────────────┐
                  │  Segment 3  │  Serialize response, return
                  └─────────────┘
```

---

## 2. What `await` Does

### The Mechanics of Suspension and Resumption

`await` does exactly three things:

1. **Starts the I/O operation** (sends the network request, issues the DB query)
2. **Suspends the current coroutine** -- returns control to the event loop
3. **Resumes the coroutine** when the I/O operation completes -- the result is now available

```python
# What you write:
result = await session.execute(select(Patient).where(Patient.id == 1))

# What happens at runtime:
#
# 1. session.execute() sends SQL to PostgreSQL via asyncpg
#    asyncpg writes bytes to the TCP socket → non-blocking
#
# 2. The coroutine SUSPENDS. Control returns to the event loop.
#    The event loop notes: "resume this coroutine when socket has data"
#
# 3. Event loop runs other coroutines (other requests, other awaits)
#
# 4. PostgreSQL sends response bytes back on the socket
#    OS signals the event loop: "this socket has data"
#
# 5. Event loop RESUMES the coroutine. result now contains the DB response.
```

AI DOCTOR EXAMPLE:
In `briefings.py` line 25: `patient = await get_patient_by_id(session, patient_id)`. When this line executes:
1. asyncpg sends `SELECT * FROM patients WHERE id = $1` to PostgreSQL
2. The coroutine handling this HTTP request suspends
3. If another doctor's briefing request arrives during the ~5ms DB query, the event loop starts processing that request
4. PostgreSQL responds, the event loop resumes the original coroutine, `patient` now contains the result

### Tracing `await` Through the AI Doctor Stack

Here is the full suspension chain for a briefing request:

```
POST /api/v1/patients/1/briefing arrives

briefings.py:
│
├── await get_patient_by_id(session, 1)     ← SUSPEND (DB query, ~5ms)
│   └── [event loop runs other requests]
│   └── [DB responds, RESUME]
│
├── await generate_briefing(patient)        ← enters briefing_service.py
│   │
│   └── async for message in query(prompt, options)
│       │
│       ├── [SDK sends prompt to Claude]    ← SUSPEND (Claude API, ~3-8s)
│       │   └── [event loop runs other requests for 3-8 seconds!]
│       │   └── [Claude responds, RESUME]
│       │
│       ├── [SDK yields ResultMessage]
│       └── [loop exits]
│
└── return BriefingResponse(...)            ← response sent to client
```

The critical insight: during the 3-8 second Claude API call, the event loop is **free to process dozens of other requests**. The single-threaded server isn't blocked -- only this one coroutine is suspended.

---

## 3. The Event Loop

### What It Is

The event loop is a **scheduler for coroutines**. It runs on a single thread and does three things in an infinite loop:

1. **Poll the OS** for completed I/O operations (using `epoll` on Linux, `kqueue` on macOS)
2. **Resume** the coroutines whose I/O completed
3. **Run** each coroutine until it hits the next `await` (then the coroutine suspends and the loop continues)

### Pseudocode

```python
# Simplified event loop -- this is what asyncio does internally:

ready_queue = []      # coroutines ready to run
io_watchers = {}      # {file_descriptor: coroutine} waiting for I/O

while True:
    # 1. Ask the OS: "Which I/O operations completed?"
    #    This is the ONLY place the loop might briefly block (waiting for OS)
    completed = os.poll(io_watchers, timeout=0)

    # 2. Move completed I/O watchers to the ready queue
    for fd, coroutine in completed:
        ready_queue.append(coroutine)
        del io_watchers[fd]

    # 3. Run each ready coroutine until it suspends or finishes
    while ready_queue:
        coroutine = ready_queue.pop(0)
        result = coroutine.send(None)  # resume the coroutine

        if result.type == "io_wait":
            # Coroutine hit an await on I/O -- register and move on
            io_watchers[result.fd] = coroutine
        elif result.type == "done":
            # Coroutine finished -- deliver the result
            deliver_response(result.value)
```

### Cooperative Multitasking

The event loop uses **cooperative** multitasking. This means coroutines must **voluntarily** yield control via `await`. Unlike threads (where the OS can preempt a thread at any time), a coroutine runs uninterrupted until it hits `await`.

This has a critical consequence: **if a coroutine never awaits, it blocks the entire event loop.**

```python
# GOOD: Coroutine yields control during I/O
async def good_endpoint():
    data = await fetch_from_api()  # suspends, loop runs other coroutines
    return process(data)

# BAD: Coroutine monopolizes the event loop
async def bad_endpoint():
    result = 0
    for i in range(10_000_000):
        result += heavy_computation(i)  # CPU work, no await, loop is FROZEN
    return result
```

In the bad example, while `bad_endpoint` is crunching numbers, **every other request in the server is paused**. No other coroutine can run. The server appears frozen. This is explored in Section 6 (Common Pitfalls).

### What `asyncio.run()` Does

`asyncio.run()` is the **entry point** that creates the event loop and runs a single coroutine:

```python
import asyncio

async def main():
    result = await some_async_function()
    return result

# asyncio.run() does three things:
# 1. Creates a NEW event loop
# 2. Runs main() on that loop until it completes
# 3. Shuts down the loop and cleans up
asyncio.run(main())
```

**You use `asyncio.run()` only in standalone scripts** -- the top-level entry point. Inside FastAPI, uvicorn already created the event loop. Your endpoint coroutines are already running on it. Calling `asyncio.run()` inside a running event loop crashes with `RuntimeError: This event loop is already running`.

AI DOCTOR EXAMPLE:
In `briefing_service.py` lines 223-227, the `if __name__ == "__main__"` block uses `asyncio.run(main())` to run the service as a standalone script. This is correct -- it is a standalone script, not a FastAPI endpoint. Inside the endpoint at `briefings.py`, you just `await generate_briefing(patient)` because the event loop already exists (uvicorn created it).

---

## 4. `asyncio.gather()` -- Concurrent I/O

### The Most Important Tool for RAG Endpoints

`asyncio.gather()` takes multiple coroutines and runs them **concurrently**. It starts all of them, lets them all await I/O in parallel, and returns all results when the last one completes:

```python
import asyncio

# SEQUENTIAL -- each await blocks until the previous completes:
async def sequential():
    a = await fetch_a()   # 100ms wait
    b = await fetch_b()   # 100ms wait
    c = await fetch_c()   # 100ms wait
    # Total: ~300ms

# CONCURRENT -- all three awaits overlap:
async def concurrent():
    a, b, c = await asyncio.gather(
        fetch_a(),   # 100ms ┐
        fetch_b(),   # 100ms ├─ all running concurrently
        fetch_c(),   # 100ms ┘
    )
    # Total: ~100ms (bounded by the slowest)
```

### Timeline Visualization

```
Sequential:

fetch_a: [──── 100ms ────]
fetch_b:                   [──── 100ms ────]
fetch_c:                                    [──── 100ms ────]
Total:   |──────────────── 300ms ──────────────────────────|


Concurrent (gather):

fetch_a: [──── 100ms ────]
fetch_b: [──── 100ms ────]
fetch_c: [──── 100ms ────]
Total:   |── 100ms ──|
```

### How It Works

```python
a, b, c = await asyncio.gather(fetch_a(), fetch_b(), fetch_c())

# Step by step:
#
# 1. gather() receives three coroutine objects
# 2. It schedules ALL THREE on the event loop immediately
# 3. Each coroutine starts and hits its first await (network request)
# 4. All three are now suspended, waiting for I/O
# 5. The OS handles all three network requests in parallel
# 6. As each completes, the event loop resumes that coroutine
# 7. When ALL THREE have completed, gather() returns the results
# 8. Results are in the same order as the arguments (a=fetch_a, b=fetch_b, c=fetch_c)
```

### When to Use `gather()` -- The Dependency Graph Rule

Use `gather()` when coroutines are **independent** -- neither needs the other's result:

```python
# CAN use gather (independent):
patient, settings = await asyncio.gather(
    get_patient(session, id),     # doesn't need settings
    get_user_settings(session),   # doesn't need patient
)

# CANNOT use gather (dependent):
embeddings = await embed_text(query)           # must complete first
results = await qdrant.search(embeddings)      # needs embeddings as input
```

AI DOCTOR EXAMPLE:
In the RAG pipeline, embedding the query and searching Qdrant are **dependent** (search needs the embedding vector). But if the agent makes two tool calls -- "search diabetes guidelines" AND "search drug interactions" -- those two searches are **independent** and can run via `gather()`. This saves 50-100ms per request.

---

## 5. `asyncio.run()` vs `await` vs `create_task()` vs `gather()`

### Quick Reference

| Function | What It Does | Use When |
|----------|-------------|----------|
| `asyncio.run(coro)` | Creates event loop, runs one coroutine, shuts down loop | Standalone scripts (`if __name__ == "__main__"`) |
| `await coro` | Suspends current coroutine, runs `coro`, resumes when done | One thing at a time, sequential flow |
| `asyncio.gather(a, b, c)` | Runs multiple coroutines concurrently, returns all results | Multiple independent I/O operations |
| `asyncio.create_task(coro)` | Schedules coroutine to run "in the background", returns a Task | Fire-and-forget, or collect result later |

### `asyncio.run()` -- Entry Point Only

```python
# STANDALONE SCRIPT (you manage the loop):
async def ingest_documents():
    chunks = await load_and_chunk("guidelines.pdf")
    embeddings = await embed_batch(chunks)
    await qdrant.upsert(embeddings)

if __name__ == "__main__":
    asyncio.run(ingest_documents())  # correct: no loop exists yet

# INSIDE FASTAPI (loop already exists):
@router.post("/{patient_id}/briefing")
async def create_briefing(patient_id: int):
    # asyncio.run(something())  # WRONG: crashes -- loop already running
    result = await something()   # CORRECT: use await
    return result
```

### `create_task()` -- Schedule and Continue

```python
async def create_briefing(patient_id: int, session: AsyncSession):
    patient = await get_patient_by_id(session, patient_id)

    # Start briefing generation but don't wait yet
    briefing_task = asyncio.create_task(generate_briefing(patient))

    # Do other work while briefing generates
    audit_task = asyncio.create_task(log_audit_event(patient_id))

    # Now wait for both
    briefing = await briefing_task
    await audit_task

    return briefing
```

`create_task()` is like `gather()` but gives you more control -- you can start tasks at different times and collect results individually.

### Decision Flowchart

```
Need to run an async function?
│
├── Am I at the top level (script, __main__)? ──→ asyncio.run()
│
├── Am I inside an async function?
│   │
│   ├── One operation, wait for result? ──→ await coro
│   │
│   ├── Multiple independent operations, need all results? ──→ asyncio.gather()
│   │
│   └── Start something, collect result later? ──→ asyncio.create_task()
│
└── Am I inside a sync function? ──→ You can't await. Refactor to async,
                                     or use run_in_executor() as escape hatch.
```

---

## 6. Common Pitfalls

### Pitfall 1: Blocking the Event Loop with Sync Code

The most common and most damaging mistake:

```python
import time
import requests  # sync HTTP library!

# WRONG: Blocks the event loop for 5 seconds
async def bad_sleep():
    time.sleep(5)  # thread sleeps, event loop FROZEN for 5 seconds
    return "done"

# RIGHT: Suspends coroutine, event loop runs others
async def good_sleep():
    await asyncio.sleep(5)  # coroutine suspended, loop free
    return "done"

# WRONG: Blocks the event loop during HTTP call
async def bad_fetch():
    response = requests.get("https://api.example.com/data")  # BLOCKS!
    return response.json()

# RIGHT: Uses async HTTP client
async def good_fetch():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")  # suspends
    return response.json()
```

**Why this is dangerous:** While `time.sleep(5)` or `requests.get()` is blocking, *every other request in the server is frozen*. 100 concurrent users all stop receiving responses because one coroutine is holding up the event loop.

### Pitfall 2: Forgetting to `await`

```python
# WRONG: Coroutine created but never executed
async def create_briefing(patient_id: int, session: AsyncSession):
    patient = get_patient_by_id(session, patient_id)  # missing await!
    # patient is a coroutine object, not a Patient
    # Python will warn: "RuntimeWarning: coroutine was never awaited"

# RIGHT:
async def create_briefing(patient_id: int, session: AsyncSession):
    patient = await get_patient_by_id(session, patient_id)
    # patient is now a Patient object
```

### Pitfall 3: Calling `asyncio.run()` Inside a Running Loop

```python
# WRONG: Crashes inside FastAPI endpoint
@router.post("/briefing")
async def create_briefing():
    result = asyncio.run(generate_briefing())  # RuntimeError!
    return result

# RIGHT:
@router.post("/briefing")
async def create_briefing():
    result = await generate_briefing()
    return result
```

### Pitfall 4: CPU-Heavy Work Without `run_in_executor()`

```python
# WRONG: Blocks the event loop during CPU work
async def process_document(content: str):
    chunks = chunk_document(content)  # CPU-heavy, no await, loop frozen
    return chunks

# RIGHT: Offload to thread pool
async def process_document(content: str):
    loop = asyncio.get_event_loop()
    chunks = await loop.run_in_executor(None, chunk_document, content)
    return chunks
```

`run_in_executor()` runs the sync function in a thread pool and wraps it in an awaitable. The event loop continues running other coroutines while the thread crunches numbers.

### Pitfall 5: Sequential Awaits When Gather Would Work

```python
# SLOW: 200ms total (100ms + 100ms)
async def slow():
    a = await fetch_guidelines("diabetes")
    b = await fetch_guidelines("hypertension")
    return a, b

# FAST: 100ms total (overlapped)
async def fast():
    a, b = await asyncio.gather(
        fetch_guidelines("diabetes"),
        fetch_guidelines("hypertension"),
    )
    return a, b
```

Always ask: "Do these awaits depend on each other?" If not, use `gather()`.

### Summary Table of Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| `time.sleep()` in async | Server freezes for N seconds | Use `await asyncio.sleep()` |
| `requests.get()` in async | Server freezes during HTTP call | Use `httpx.AsyncClient()` with `await` |
| Missing `await` | Coroutine object instead of result | Add `await` keyword |
| `asyncio.run()` in endpoint | `RuntimeError: loop already running` | Use `await` instead |
| CPU-heavy code in coroutine | Event loop frozen, all requests stall | Use `run_in_executor()` |
| Sequential awaits | Unnecessarily slow endpoint | Use `asyncio.gather()` for independent operations |

---

## 7. Summary

```
COROUTINES AND THE EVENT LOOP:

1. async def creates a coroutine function (pausable function)
2. await SUSPENDS the coroutine and returns control to the event loop
3. The event loop polls the OS for I/O completion
4. When I/O completes, the event loop RESUMES the coroutine
5. asyncio.gather() runs multiple coroutines concurrently
6. asyncio.run() creates the loop (scripts only -- uvicorn creates it for FastAPI)
7. Never block the event loop with sync I/O or CPU work
```

| Concept | What It Is | Analogy |
|---------|-----------|---------|
| Coroutine | Pausable function | Recipe that a chef can set aside and come back to |
| `await` | Pause point | Chef says "this needs to bake for 10 minutes, let me start another dish" |
| Event loop | Scheduler | The chef managing multiple dishes on different timers |
| `asyncio.gather()` | Concurrent execution | Put three dishes in the oven at the same time |
| `asyncio.run()` | Bootstrap | Opening the kitchen for the day (only once) |

---

**Next**: `03-FASTAPI-ASYNC-ARCHITECTURE.md` -- How FastAPI, uvicorn, and ASGI connect these concepts into a production web server.
