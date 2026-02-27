# Async Patterns for RAG Pipelines

**Part 4 of 5: Async Server Architecture Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Learning Objectives](#learning-objectives)
2. [Anatomy of a RAG Request](#1-anatomy-of-a-rag-request)
3. [Sequential vs Concurrent I/O in RAG](#2-sequential-vs-concurrent-io-in-rag)
4. [Async Qdrant Client](#3-async-qdrant-client)
5. [Async Embedding Calls](#4-async-embedding-calls)
6. [The Multi-Turn Agent Loop](#5-the-multi-turn-agent-loop)
7. [Profiling and Optimizing Async Endpoints](#6-profiling-and-optimizing-async-endpoints)
8. [Async Antipatterns in RAG](#7-async-antipatterns-in-rag)
9. [Summary](#8-summary)

---

## Learning Objectives

After reading this document, you will understand:

- How to **map the I/O dependency graph** of a RAG request to identify concurrent vs sequential operations
- When to use `asyncio.gather()` for **parallel I/O** within a single RAG request
- How to use the **async Qdrant client** (`AsyncQdrantClient`) correctly
- How to design **async embedding calls** for both online queries and batch ingestion
- How the agent's **multi-turn tool loop** creates cascading async I/O patterns
- How to **profile** async RAG endpoints and identify bottlenecks
- The **antipatterns** that silently break async performance in RAG systems

Key mental models to internalize:

- A RAG request is a **pipeline of I/O waits**. Each stage (embed, search, generate) is I/O-bound. Async lets the server serve other users during each wait.
- **Within one request**, independent I/O operations can run concurrently with `gather()`. **Across requests**, the event loop automatically interleaves. These are two separate benefits.
- The agent's multi-turn loop (think → tool call → tool result → think) is a sequence of `await`s. Each `await` frees the event loop for other requests.

Common misconceptions to avoid:

- "My RAG endpoint is slow so I need more workers" -- If the bottleneck is I/O wait (Claude API latency), more async concurrency helps more than more processes. Workers help CPU-bound work.
- "`asyncio.gather()` makes everything faster" -- Only independent operations benefit. Dependent operations (search depends on embedding) must be sequential.
- "I should parallelize everything" -- No. First map the dependency graph. Over-parallelizing dependent operations causes errors, not speedups.

---

## 1. Anatomy of a RAG Request

### The Full I/O Chain

When `POST /api/v1/patients/1/briefing` arrives, the RAG-augmented request does this:

```
┌─────────────────────────────────────────────────────────────────┐
│  POST /api/v1/patients/1/briefing                               │
│                                                                  │
│  1. [await get_patient_by_id()]          PostgreSQL   ~5ms       │
│                                                                  │
│  2. [await query(prompt, options)]       Claude Agent  ~8-12s    │
│      │                                                           │
│      ├── Agent thinks, decides to search                         │
│      │                                                           │
│      ├── Tool call: search("diabetes management")                │
│      │   ├── [await embed_text(query)]   Vertex AI    ~100-200ms │
│      │   └── [await qdrant.search()]     Qdrant       ~10-50ms   │
│      │                                                           │
│      ├── Agent reads results, decides to search again            │
│      │                                                           │
│      ├── Tool call: search("metformin renal dosing")             │
│      │   ├── [await embed_text(query)]   Vertex AI    ~100-200ms │
│      │   └── [await qdrant.search()]     Qdrant       ~10-50ms   │
│      │                                                           │
│      ├── Agent has enough context, generates briefing            │
│      │   └── [await Claude generation]   Claude       ~3-5s      │
│      │                                                           │
│      └── ResultMessage with structured output                    │
│                                                                  │
│  Total wall time: ~8-12 seconds                                  │
│  Time doing CPU work: <10ms                                      │
│  Time waiting on I/O: ~8-12 seconds (99.9%)                     │
└─────────────────────────────────────────────────────────────────┘
```

### Annotating Each Step

| Step | Operation | I/O-Bound? | Async? | Can Overlap? |
|------|-----------|-----------|--------|-------------|
| 1 | Fetch patient from PostgreSQL | Yes | `await session.execute()` | No (needed before agent call) |
| 2a | Agent thinking (Claude API) | Yes | `async for` yields | Overlaps with other requests |
| 2b | Embed query (Vertex AI) | Yes | `await embed_text()` | Within tool -- sequential with search |
| 2c | Search Qdrant | Yes | `await qdrant.search()` | Depends on embedding result |
| 2d | Agent reads + generates | Yes | `async for` yields | Overlaps with other requests |

**Key observation:** Steps 2b and 2c are sequential within a single tool call (search needs the embedding). But if the agent makes two independent tool calls, those tool calls could overlap via `gather()`.

---

## 2. Sequential vs Concurrent I/O in RAG

### The Dependency Graph

Not all I/O operations in a RAG pipeline are independent. The first step is to map what depends on what:

```
get_patient() ──────────────────────────┐
                                        ▼
                                   query(prompt)
                                        │
                              ┌─────────┴─────────┐
                              ▼                    ▼
                    Tool call 1:              Tool call 2:
                    "diabetes management"     "metformin renal dosing"
                         │                        │
                         ▼                        ▼
                    embed_text()              embed_text()
                         │                        │
                         ▼                        ▼
                    qdrant.search()           qdrant.search()
                         │                        │
                         └─────────┬──────────────┘
                                   ▼
                         Agent generates output

Legend:
  │ = depends on (must be sequential)
  Tool call 1 and 2 are INDEPENDENT (if agent issues both)
```

### Where Concurrency IS Possible

**Scenario 1: Agent issues multiple tool calls**

The Claude Agent SDK supports multi-tool use -- the agent can request multiple tool calls in a single turn. If it asks for "diabetes guidelines" AND "drug interactions" simultaneously, your tool handler can execute them in parallel:

```python
async def handle_tool_calls(tool_calls: list[ToolCall]) -> list[ToolResult]:
    # If agent issues multiple independent tool calls,
    # execute them concurrently:
    results = await asyncio.gather(
        *[execute_tool(call) for call in tool_calls]
    )
    return results
```

**Scenario 2: Batch embedding during ingestion**

When ingesting 100 documents, you embed each chunk. These embeddings are independent:

```python
async def embed_batch(texts: list[str], batch_size: int = 10) -> list[list[float]]:
    """Embed texts in parallel batches."""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        # Embed all chunks in this batch concurrently
        embeddings = await asyncio.gather(
            *[embed_text(text) for text in batch]
        )
        all_embeddings.extend(embeddings)
    return all_embeddings
```

**Scenario 3: Pre-fetching**

If you know you will need both the patient record and some setup data:

```python
async def create_briefing(patient_id: int, session: AsyncSession):
    # Fetch patient and load collection info concurrently
    patient, collection_info = await asyncio.gather(
        get_patient_by_id(session, patient_id),
        qdrant.get_collection("clinical_guidelines"),
    )
    # Both are ready, proceed with agent call
    return await generate_briefing(patient)
```

### Where Concurrency Is NOT Possible

```python
# CANNOT parallelize: search depends on embedding
embedding = await embed_text("diabetes management")   # must complete first
results = await qdrant.search(embedding)               # needs the embedding

# CANNOT parallelize: agent call depends on patient record
patient = await get_patient_by_id(session, 1)          # must complete first
briefing = await generate_briefing(patient)             # needs the patient data
```

**Rule: draw the dependency graph first. Only `gather()` operations that have no edges between them.**

---

## 3. Async Qdrant Client

### `QdrantClient` vs `AsyncQdrantClient`

Qdrant's Python library provides both sync and async clients. In a FastAPI async endpoint, **always use `AsyncQdrantClient`**:

```python
from qdrant_client import AsyncQdrantClient

# Initialize once at startup (e.g., in config or lifespan)
qdrant_client = AsyncQdrantClient(url="http://localhost:6333")

# Use in async endpoint or service
async def search(query_vector: list[float], limit: int = 5):
    results = await qdrant_client.search(
        collection_name="clinical_guidelines",
        query_vector=query_vector,
        limit=limit,
    )
    return results
```

### Why Not the Sync Client?

```python
from qdrant_client import QdrantClient

# DANGEROUS in async endpoints:
sync_client = QdrantClient(url="http://localhost:6333")

async def bad_search(query_vector: list[float]):
    # This BLOCKS the event loop for 10-50ms
    results = sync_client.search(
        collection_name="clinical_guidelines",
        query_vector=query_vector,
        limit=5,
    )
    return results
```

The sync client uses `requests` internally -- a blocking HTTP library. Inside an `async def` endpoint, this freezes the event loop during the Qdrant round-trip. With 50 concurrent requests, they serialize instead of overlapping.

### Connection Pooling

`AsyncQdrantClient` maintains an internal `httpx.AsyncClient` with connection pooling:

```
┌──────────────────────────────────────────────┐
│  AsyncQdrantClient                           │
│                                              │
│  Internal httpx.AsyncClient:                 │
│  ├── Connection 1 → Qdrant :6333             │
│  ├── Connection 2 → Qdrant :6333             │
│  └── Connection 3 → Qdrant :6333             │
│                                              │
│  Multiple coroutines can issue searches      │
│  concurrently through the connection pool.   │
│  Each search suspends while waiting for      │
│  Qdrant to respond.                          │
└──────────────────────────────────────────────┘
```

AI DOCTOR EXAMPLE:
The planned `rag_service.py` will use `AsyncQdrantClient` initialized at module level (or via FastAPI lifespan). When the agent calls `search_clinical_guidelines`, the tool handler calls `await qdrant_client.search()`, which suspends the coroutine during the Qdrant round-trip. If two agents are searching simultaneously (two doctors requesting briefings), both searches proceed concurrently through the connection pool.

---

## 4. Async Embedding Calls

### Online Query Embedding (Single Text)

During a search tool call, you embed a single query string. This is a straightforward async call:

```python
from google.cloud import aiplatform

async def embed_text(text: str) -> list[float]:
    """Embed a single text string via Vertex AI."""
    # The Vertex AI SDK call -- await suspends during the API call
    model = TextEmbeddingModel.from_pretrained("text-embedding-005")
    embeddings = await model.get_embeddings_async([text])
    return embeddings[0].values
```

The `await` suspends the coroutine for ~100-200ms while Vertex AI computes the embedding. During that time, the event loop handles other requests.

### Batch Embedding During Ingestion

Ingesting 100 documents with 500 chunks total requires 500 embedding calls. Sequential would take 500 × 150ms = 75 seconds. With batching + `gather()`:

```python
async def embed_and_upsert(chunks: list[DocumentChunk], batch_size: int = 20):
    """Embed chunks in concurrent batches and upsert to Qdrant."""
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]

        # Embed all chunks in this batch concurrently
        embeddings = await asyncio.gather(
            *[embed_text(chunk.text) for chunk in batch]
        )

        # Prepare points for Qdrant
        points = [
            PointStruct(
                id=str(uuid4()),
                vector=embedding,
                payload=chunk.model_dump(),
            )
            for chunk, embedding in zip(batch, embeddings)
        ]

        # Upsert batch to Qdrant
        await qdrant_client.upsert(
            collection_name="clinical_guidelines",
            points=points,
        )

    # 500 chunks / 20 per batch = 25 batches
    # Each batch: 20 concurrent embeds (~150ms) + 1 upsert (~50ms) = ~200ms
    # Total: 25 × 200ms = ~5 seconds (vs 75 seconds sequential!)
```

```
Sequential embedding (500 chunks):
[embed 1: 150ms][embed 2: 150ms][embed 3: 150ms]...[embed 500: 150ms]
Total: ~75 seconds

Batched + concurrent (batch_size=20):
[───── 20 embeds concurrently: 150ms ─────][upsert: 50ms]
[───── 20 embeds concurrently: 150ms ─────][upsert: 50ms]
... × 25 batches
Total: ~5 seconds
```

AI DOCTOR EXAMPLE:
The `scripts/ingest_docs.py` CLI tool will use `asyncio.run()` to start the event loop, then call the batch embedding function to ingest clinical guidelines. Even though it is a script (not a server), async + `gather()` speeds up ingestion by 15x. The script processes the ADA Standards of Care (28 chunks) in under a second instead of ~4 seconds.

---

## 5. The Multi-Turn Agent Loop

### How the Agent Creates Cascading Async I/O

With RAG, the agent operates in a multi-turn loop (`max_turns=4`). Each turn involves I/O:

```
Turn 1: Agent receives patient record, thinks, decides to search
        └── I/O: Claude API call (~2-3s)

Turn 2: Agent calls search tool
        └── Tool I/O: embed (~150ms) + Qdrant search (~30ms)
        Agent reads results, decides to search again
        └── I/O: Claude API call (~2-3s)

Turn 3: Agent calls another search tool
        └── Tool I/O: embed (~150ms) + Qdrant search (~30ms)
        Agent has enough context, generates structured output
        └── I/O: Claude API call (~3-5s)

Turn 4: Agent returns ResultMessage with PatientBriefing
```

### Two Concurrent Briefing Requests

The event loop interleaves these multi-turn loops across requests:

```
Doctor A requests briefing (Patient 1):
Doctor B requests briefing (Patient 2):

Event loop timeline:

[A: fetch patient] ← suspend (DB)
[B: fetch patient] ← suspend (DB)
[A: resume, call agent] ← suspend (Claude thinking, Turn 1)
[B: resume, call agent] ← suspend (Claude thinking, Turn 1)
  ─── idle (both waiting on Claude) ───
[A: resume, agent wants tool] [A: embed+search] ← suspend (Vertex+Qdrant)
[B: resume, agent wants tool] [B: embed+search] ← suspend (Vertex+Qdrant)
  ─── idle (both waiting on APIs) ───
[A: resume, feed results to agent] ← suspend (Claude, Turn 2)
[B: resume, feed results to agent] ← suspend (Claude, Turn 2)
  ─── idle ───
[A: resume, agent generates output] → return to Doctor A
[B: resume, agent generates output] → return to Doctor B

Total: ~10 seconds for BOTH requests (not 20 seconds!)
```

Neither doctor blocks the other. Every `await` in the pipeline is a chance for the event loop to advance the other request. The server processes both briefings in roughly the same wall time as one.

### When the Agent Issues Multiple Tool Calls

If the agent requests two searches in one turn (multi-tool use), execute them concurrently:

```python
async def handle_tool_calls(tool_calls: list[ToolCall]) -> list[ToolResult]:
    """Execute multiple agent tool calls concurrently."""
    if len(tool_calls) == 1:
        return [await execute_single_tool(tool_calls[0])]

    # Multiple independent tool calls -- run in parallel
    results = await asyncio.gather(
        *[execute_single_tool(call) for call in tool_calls]
    )
    return list(results)


async def execute_single_tool(call: ToolCall) -> ToolResult:
    """Execute one tool call (embed + search)."""
    query_vector = await embed_text(call.arguments["query"])
    results = await qdrant_client.search(
        collection_name="clinical_guidelines",
        query_vector=query_vector,
        limit=call.arguments.get("max_results", 5),
    )
    formatted = format_as_xml_sources(results)
    return ToolResult(content=formatted)
```

With two independent searches:
- Sequential: embed(150ms) + search(30ms) + embed(150ms) + search(30ms) = **360ms**
- Concurrent via `gather()`: max(embed+search, embed+search) = **180ms**

---

## 6. Profiling and Optimizing Async Endpoints

### Timing Each Stage

To find bottlenecks, wrap each `await` with timing:

```python
import time
import logging

logger = logging.getLogger(__name__)

async def search(query: str, limit: int = 5) -> list[RetrievalResult]:
    t0 = time.perf_counter()
    query_vector = await embed_text(query)
    t1 = time.perf_counter()
    logger.info("Embedding took %.0fms", (t1 - t0) * 1000)

    results = await qdrant_client.search(
        collection_name="clinical_guidelines",
        query_vector=query_vector,
        limit=limit,
    )
    t2 = time.perf_counter()
    logger.info("Qdrant search took %.0fms", (t2 - t1) * 1000)

    return [to_retrieval_result(r, idx) for idx, r in enumerate(results)]
```

### Common Bottleneck Patterns

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Embedding takes 500ms+ | Network latency to Vertex AI | Check region, consider local embedding model |
| Qdrant search takes 100ms+ | Large collection without HNSW index | Check indexing threshold, tune `ef` |
| Claude API takes 10s+ | Complex prompt, large context | Trim context, use faster model for simple cases |
| All requests slow under load | Blocking call in async endpoint | Check for sync libraries (see Section 7) |
| First request slow, rest fast | Connection pool warming up | Pre-warm connections in lifespan handler |

### When Async Is NOT Your Bottleneck

If the Claude API call takes 8 seconds, no amount of async optimization changes that:

```
Request latency breakdown:
├── Fetch patient:      5ms   (0.06%)
├── Embed query:      150ms   (1.9%)
├── Qdrant search:     30ms   (0.4%)
├── Claude generation: 8000ms (97.6%)  ← the bottleneck
└── Total:           8185ms

Optimizing embed + search saves 180ms at most.
The 8 seconds of Claude API time is where the user waits.
```

For this case, async is still the right choice (other requests aren't blocked), but the **latency improvement** for individual requests comes from:
- Prompt optimization (shorter context → faster generation)
- Model selection (Haiku for simple cases, Opus for complex)
- Prompt caching (see `agent-arch/03-PROMPT-CACHING-AND-OPTIMIZATION.md`)

---

## 7. Async Antipatterns in RAG

### The Antipattern Table

| Antipattern | What Goes Wrong | Fix |
|------------|-----------------|-----|
| Sync Qdrant client in async endpoint | `QdrantClient` uses `requests` internally → blocks event loop for 10-50ms per search | Use `AsyncQdrantClient` |
| `requests.get()` in async endpoint | Blocks event loop during HTTP call | Use `httpx.AsyncClient` with `await` |
| `time.sleep()` in async endpoint | Freezes entire event loop | Use `await asyncio.sleep()` |
| `asyncio.run()` inside endpoint | Crashes: "event loop already running" | Use `await` directly |
| Sequential awaits for independent ops | Endpoint is slower than necessary | Use `asyncio.gather()` |
| CPU-heavy parsing in coroutine | Event loop blocked during parsing | Use `await loop.run_in_executor()` |
| No connection pooling | New TCP connection per Qdrant query | Reuse `AsyncQdrantClient` instance |
| Embedding one text at a time during ingestion | 500 serial API calls instead of batched | Batch with `asyncio.gather()` |
| Sync file I/O in async endpoint | `open()` and `read()` block event loop | Use `aiofiles` or `run_in_executor()` |

### Detailed Examples

**Antipattern: Sync Qdrant Client**

```python
# WRONG:
from qdrant_client import QdrantClient
sync_client = QdrantClient(url="http://localhost:6333")

async def search_tool(query: str):
    embedding = await embed_text(query)
    # This blocks the event loop for 10-50ms!
    results = sync_client.search("clinical_guidelines", embedding, limit=5)
    return results

# RIGHT:
from qdrant_client import AsyncQdrantClient
async_client = AsyncQdrantClient(url="http://localhost:6333")

async def search_tool(query: str):
    embedding = await embed_text(query)
    # This suspends the coroutine, event loop stays free
    results = await async_client.search("clinical_guidelines", embedding, limit=5)
    return results
```

**Antipattern: CPU-Heavy Document Parsing**

```python
# WRONG: Blocks event loop during heavy parsing
async def ingest_document(file_path: str):
    # parse_pdf() is CPU-heavy (PyMuPDF, unstructured)
    # No await → runs on event loop thread → blocks everything
    elements = parse_pdf(file_path)
    chunks = chunk_elements(elements)
    ...

# RIGHT: Offload to thread pool
async def ingest_document(file_path: str):
    loop = asyncio.get_event_loop()
    # CPU work runs in a thread; event loop stays free
    elements = await loop.run_in_executor(None, parse_pdf, file_path)
    chunks = await loop.run_in_executor(None, chunk_elements, elements)
    ...
```

AI DOCTOR EXAMPLE:
During document ingestion via `scripts/ingest_docs.py`, parsing PDFs with `unstructured` is CPU-heavy (10-100ms per page). If this runs inside an async endpoint (future API upload feature), it must use `run_in_executor()` to avoid blocking the event loop. For the CLI script, it doesn't matter (no event loop serving other requests), but the function should still be designed for async reuse.

---

## 8. Summary

```
ASYNC PATTERNS FOR THE AI DOCTOR RAG PIPELINE:

1. Map the dependency graph before parallelizing
   - embed → search: sequential (search needs the vector)
   - tool call A vs tool call B: concurrent (independent)

2. Use AsyncQdrantClient, never sync QdrantClient
   - Same API, async-native, connection pooled

3. Use asyncio.gather() for:
   - Multiple independent tool calls
   - Batch embedding during ingestion
   - Pre-fetching (patient + collection info)

4. Use await (sequential) for:
   - Dependent operations (embed then search)
   - Agent turns (each turn depends on the previous)

5. Profile each stage to find the real bottleneck
   - Usually: Claude API >> embed >> Qdrant search
   - Optimize the biggest number, not the easiest one

6. Never block the event loop
   - No sync HTTP clients, no time.sleep(), no CPU work without executor
```

| Pattern | When to Use | Example |
|---------|------------|---------|
| `await f()` | Dependent, sequential operation | `embedding = await embed(q)` then `await search(embedding)` |
| `await gather(f(), g())` | Independent, concurrent I/O | Two tool calls, batch embeddings |
| `run_in_executor(fn)` | CPU-heavy sync work | PDF parsing, chunking |
| `AsyncQdrantClient` | All Qdrant operations in async code | Search, upsert, collection management |
| Batch + `gather()` | Many similar independent operations | Ingesting 500 chunks |

---

**Previous**: `03-FASTAPI-ASYNC-ARCHITECTURE.md` -- How FastAPI, uvicorn, and ASGI connect async concepts into a production server.

**Related**: `docs/RAG-ARCH.md` -- The full RAG architecture this document teaches you to implement with async patterns.
