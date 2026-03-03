# Vector Databases and Embeddings

**Part 4 of 11: Agent Architecture & AI Model Internals Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Learning Objectives](#learning-objectives)
2. [From Text to Vectors — Why Embeddings Exist](#1-from-text-to-vectors--why-embeddings-exist)
   - [The Keyword Search Problem](#the-keyword-search-problem)
   - [Semantic Meaning as Geometry](#semantic-meaning-as-geometry)
   - [The Classic Analogy: King - Man + Woman = Queen](#the-classic-analogy-king---man--woman--queen)
   - [Why This Matters for Retrieval](#why-this-matters-for-retrieval)
3. [How Embedding Models Work](#2-how-embedding-models-work)
   - [From Transformer Internals to Embedding APIs](#from-transformer-internals-to-embedding-apis)
   - [Task Types: RETRIEVAL_QUERY vs RETRIEVAL_DOCUMENT](#task-types-retrieval_query-vs-retrieval_document)
   - [Our Embedding Code](#our-embedding-code)
4. [Embedding Model Selection](#3-embedding-model-selection)
   - [MTEB Benchmarks](#mteb-benchmarks)
   - [Dimension Tradeoffs](#dimension-tradeoffs)
   - [Why We Chose text-embedding-005](#why-we-chose-text-embedding-005)
   - [Alternative Models](#alternative-models)
5. [Vector Similarity and Distance Metrics](#4-vector-similarity-and-distance-metrics)
   - [Cosine Similarity](#cosine-similarity)
   - [Dot Product](#dot-product)
   - [L2 / Euclidean Distance](#l2--euclidean-distance)
   - [Which Metric to Use](#which-metric-to-use)
   - [Visualizing Similarity in 2D](#visualizing-similarity-in-2d)
6. [Vector Database Architecture](#5-vector-database-architecture)
   - [Why Not Just Use SQL?](#why-not-just-use-sql)
   - [Approximate Nearest Neighbors (ANN)](#approximate-nearest-neighbors-ann)
   - [HNSW — The Algorithm Behind Modern Vector Search](#hnsw--the-algorithm-behind-modern-vector-search)
   - [Vector Database Comparison](#vector-database-comparison)
7. [Qdrant — Our Vector Store](#6-qdrant--our-vector-store)
   - [Why Qdrant](#why-qdrant)
   - [Core Concepts](#core-concepts)
   - [Docker Setup](#docker-setup)
   - [Collection Creation](#collection-creation)
   - [Payload Indexes and Filtered Search](#payload-indexes-and-filtered-search)
   - [Search Implementation](#search-implementation)
8. [Indexing and Performance](#7-indexing-and-performance)
   - [Deterministic IDs with UUID5](#deterministic-ids-with-uuid5)
   - [Idempotent Upserts](#idempotent-upserts)
   - [In-Memory Qdrant for Testing](#in-memory-qdrant-for-testing)
   - [Score Thresholds](#score-thresholds)
   - [Batch Embedding Performance](#batch-embedding-performance)
9. [Next Steps](#next-steps)

---

## Learning Objectives

After reading this document, you will be able to:

- **Explain** why semantic search requires embeddings rather than keyword matching
- **Describe** how embedding models convert text into high-dimensional vectors that capture meaning
- **Distinguish** between RETRIEVAL_QUERY and RETRIEVAL_DOCUMENT task types and why they exist
- **Compare** embedding models using MTEB benchmarks and reason about dimension tradeoffs
- **Calculate** cosine similarity between vectors and explain why it is preferred for normalized embeddings
- **Explain** why vector databases use Approximate Nearest Neighbor (ANN) algorithms instead of exact search
- **Describe** the HNSW algorithm at an intuitive level — how it builds a navigable graph for fast search
- **Compare** vector databases (Qdrant, pgvector, Pinecone, Weaviate, Chroma) on key criteria
- **Trace** the AI Doctor's embedding and search pipeline from raw clinical text to scored retrieval results
- **Explain** UUID5 deterministic IDs, idempotent upserts, payload filtering, and score thresholds

**Key mental models built in this document:**

- Embeddings are coordinates in meaning-space. Nearby points have similar meaning.
- Vector search is geometry, not string matching. You are finding the closest points in a high-dimensional space.
- ANN trades a tiny amount of accuracy for orders-of-magnitude speed improvement. This tradeoff is almost always worth it.
- The embedding model and the vector database are separate concerns: one creates the vectors, the other stores and searches them.

**Common misconceptions this document addresses:**

- "Embeddings are just a fancy hash" — No. They preserve semantic relationships. Similar meanings produce nearby vectors.
- "You can use any distance metric interchangeably" — No. The choice depends on whether your vectors are normalized and how the embedding model was trained.
- "pgvector is sufficient for any scale" — It works well for small datasets (under ~100K vectors) but lacks the ANN indexing sophistication needed for millions of vectors.
- "Higher embedding dimensions are always better" — Not necessarily. Beyond a point, extra dimensions add storage cost and latency without meaningful quality improvement.

---

## 1. From Text to Vectors — Why Embeddings Exist

In [Document 02 (Transformer Architecture)](./02-TRANSFORMER-ARCHITECTURE.md), we saw how transformers convert token IDs into dense vectors called embeddings. Those embeddings are internal to the model — they exist inside the transformer's layers and are used for attention and prediction. In this document, we take a different angle: embeddings as a **standalone tool for search and retrieval**.

The core question is: how do you find documents that are *relevant* to a question, even when they do not share the same words?

---

### The Keyword Search Problem

Traditional search engines use keyword matching. When you search for "heart attack treatment," the engine looks for documents containing the exact words "heart," "attack," and "treatment." This works surprisingly well for many cases, but it fails in important ways:

```
KEYWORD SEARCH FAILURES:

Query: "heart attack treatment"
  - MISSES: "Management of acute myocardial infarction"
    (same topic, completely different words)

  - MISSES: "Therapeutic approaches for coronary events"
    (same topic, zero keyword overlap)

  - MATCHES: "The movie gave me a heart attack — what a treatment for boredom!"
    (same words, completely irrelevant meaning)
```

The fundamental problem: **words are not meaning**. The same meaning can be expressed with different words (synonymy), and the same words can express different meanings (polysemy). Keyword search operates on surface form, but retrieval should operate on meaning.

```
AI DOCTOR EXAMPLE:
A physician asks the AI Doctor: "What's the latest on managing diabetic
patients with kidney complications?"

Keyword search would look for documents containing "managing," "diabetic,"
"patients," "kidney," and "complications." It would miss a guideline titled
"Renal Protective Strategies in Type 2 Diabetes Mellitus" — even though
that document is exactly what the physician needs.

Semantic search with embeddings finds it because both the query and the
document occupy the same region of meaning-space.
```

---

### Semantic Meaning as Geometry

Embeddings solve this by converting text into vectors — lists of numbers — where **the geometric relationships between vectors mirror the semantic relationships between the texts**.

Think of it this way: every piece of text gets coordinates in a high-dimensional space. Texts with similar meaning end up near each other. Texts with different meaning end up far apart.

```
High-dimensional embedding space (shown in 2D for illustration):

                        "acute myocardial infarction"
                               ●
                              /
                             / (close — same medical concept)
                            /
      "heart attack"  ●───●  "coronary event"
                            \
                             \ (still close — related concept)
                              \
                               ● "cardiac arrest"


                                          ● "movie review"
                                         (far away — unrelated)



                 ● "diabetes management"
                /
               / (moderate distance — different medical topic)
              /
   "insulin therapy" ●
```

This is not metaphor. Embedding models really do produce vectors where distance corresponds to semantic similarity. A model trained on enough text learns that "heart attack" and "myocardial infarction" appear in similar contexts, describe the same phenomenon, and should therefore have similar vector representations.

---

### The Classic Analogy: King - Man + Woman = Queen

The most famous demonstration of embedding geometry is the word analogy task, first shown with Word2Vec:

```
vector("king") - vector("man") + vector("woman") ≈ vector("queen")
```

What does this mean? The embedding space has learned that the relationship between "king" and "man" is the same as the relationship between "queen" and "woman" — namely, the concept of gender. When you subtract the "maleness" component from "king" and add the "femaleness" component, you land near "queen."

```
Simplified 2D illustration of the analogy:

    Gender dimension →

  ↑                man ●─────────────────── ● woman
  │                    │    gender offset    │
  │                    │                     │
  Royalty              │ (same offset!)      │
  dimension            │                     │
  │                    │                     │
  │               king ●─────────────────── ● queen
  │

  king - man ≈ queen - woman  (the "royalty" component)
  king - queen ≈ man - woman  (the "gender" component)
```

This is not hand-programmed. Nobody told the model that "king" is a male royal. The model learned these relationships by observing that "king" appears in contexts similar to "queen" (royal contexts) and similar to "man" (male contexts). The geometric structure of the embedding space emerges automatically from training on large text corpora.

Modern embedding models extend this far beyond individual words. They embed entire sentences and paragraphs, capturing complex semantic relationships:

```
embed("The patient presents with chest pain and elevated troponin levels")
≈
embed("Clinical findings consistent with acute coronary syndrome")

These two sentences have almost no words in common, but their
embedding vectors are very close because they describe the same
clinical scenario.
```

---

### Why This Matters for Retrieval

This property — semantic similarity corresponds to vector proximity — is exactly what we need for search:

1. **At index time**: Convert every document (or document chunk) into a vector and store it
2. **At query time**: Convert the user's question into a vector
3. **Search**: Find the stored vectors closest to the query vector
4. **Return**: The documents whose vectors are nearest are the most semantically relevant

```
RETRIEVAL FLOW:

  "What drugs treat atrial fibrillation?"
              │
              ▼
       ┌─────────────┐
       │  Embedding   │
       │    Model     │
       └─────┬───────┘
              │
              ▼
    [0.12, -0.34, 0.56, ..., 0.23]    ← query vector (768 dims)
              │
              ▼
     ┌────────────────────┐
     │   Vector Database   │    Contains thousands of pre-computed
     │                     │    document vectors
     │  Find nearest       │
     │  neighbors          │
     └────────┬───────────┘
              │
              ▼
    Results (ranked by similarity):
    1. "Rate Control in Atrial Fibrillation" (score: 0.89)
    2. "Anticoagulation for AF Patients"     (score: 0.85)
    3. "Rhythm vs Rate Control Strategies"   (score: 0.82)
```

This is the foundation that the entire RAG (Retrieval-Augmented Generation) pipeline is built on. The next document in this series covers the full RAG pipeline. This document focuses on the two core components: the embedding model that creates vectors, and the vector database that stores and searches them.

---

## 2. How Embedding Models Work

### From Transformer Internals to Embedding APIs

In Document 02, you learned that transformers internally represent tokens as dense vectors. An **embedding model** is a transformer that has been specifically trained to produce vectors where semantic similarity maps to vector proximity.

The key difference from a generative model like Claude:

| | Generative Model (Claude) | Embedding Model (text-embedding-005) |
|---|---|---|
| **Input** | Text | Text |
| **Output** | Generated text (tokens) | A vector of floats |
| **Training objective** | Predict next token | Make similar texts have similar vectors |
| **Use case** | Conversation, reasoning, generation | Search, clustering, classification |
| **Architecture** | Decoder-only transformer | Encoder transformer (usually) |

Embedding models are typically trained with a **contrastive learning** objective. The training data consists of pairs: (query, relevant document). The model learns to produce vectors such that:

- The query vector is **close** to the relevant document's vector
- The query vector is **far** from irrelevant documents' vectors

```
CONTRASTIVE TRAINING INTUITION:

  Training pair: ("heart attack symptoms", "Chest pain, shortness of breath,
                   nausea, and sweating are common signs of acute MI")

  The model learns to push these vectors TOGETHER:

     query ●───────→ ● relevant doc     (minimize distance)

  And push these vectors APART:

     query ●                             (maximize distance)
                         ● random doc

  After millions of such examples, the model's vector space
  reflects semantic similarity across all text.
```

---

### Task Types: RETRIEVAL_QUERY vs RETRIEVAL_DOCUMENT

Google's text-embedding-005 model (which our project uses) supports **task types** that modify how text is embedded. This is a subtle but important feature.

When you embed a short query differently from a long document, the model can optimize the vector space for asymmetric retrieval — where queries are short questions and documents are long passages.

| Task Type | When to Use | What It Does |
|-----------|-------------|--------------|
| `RETRIEVAL_QUERY` | Embedding a user's search query | Optimizes vector for matching against documents |
| `RETRIEVAL_DOCUMENT` | Embedding a document chunk for indexing | Optimizes vector for being found by queries |
| `SEMANTIC_SIMILARITY` | Comparing two texts of similar length | Symmetric similarity (no query/document distinction) |
| `CLASSIFICATION` | Embedding text for a classifier | Optimizes for separating classes |
| `CLUSTERING` | Embedding text for clustering | Optimizes for grouping similar texts |

The asymmetry matters. A query like "treatment for AFib" is short and intentional. A document chunk like "The management of atrial fibrillation involves rate control with beta-blockers or calcium channel blockers, rhythm control with antiarrhythmic drugs..." is long and descriptive. The model internally adjusts its pooling and weighting strategy based on the task type.

```
AI DOCTOR EXAMPLE:
In our project, the distinction is clear and consistent:

  - At INGESTION time: clinical guideline chunks are embedded with
    task_type="RETRIEVAL_DOCUMENT"

  - At QUERY time: the physician's question is embedded with
    task_type="RETRIEVAL_QUERY"

This asymmetric embedding ensures the query vector is optimized
to "find" document vectors, not to be "similar" to them in a
symmetric sense. The difference in retrieval quality is measurable
— Google's benchmarks show 2-5% improvement on NDCG@10 when using
appropriate task types vs. using no task type.
```

---

### Our Embedding Code

Here is the actual embedding implementation from the AI Doctor backend. There are two functions: one for queries (single text, real-time) and one for documents (batch, at ingestion time).

**Query embedding** — used at search time when a physician asks a question:

```python
# backend/src/services/rag_service.py

def embed_text(text: str) -> list[float]:
    """Embed a single text string for query-time search."""
    if settings.google_api_key:
        # Direct API call with API key authentication
        vectors = _vertex_embed_via_api_key([text], "RETRIEVAL_QUERY")
        vector = vectors[0]
    else:
        # Google GenAI SDK with Application Default Credentials
        client = get_genai_client()
        response = client.models.embed_content(
            model=settings.embedding_model,        # "text-embedding-005"
            contents=[text],
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dimensions,  # 768
                task_type="RETRIEVAL_QUERY",        # <-- query task type
            ),
        )
        vector = list(response.embeddings[0].values)
    return vector
```

**Batch embedding** — used at ingestion time when processing clinical guidelines:

```python
# backend/src/services/rag_service.py

def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts for document indexing."""
    if settings.google_api_key:
        vectors = _vertex_embed_via_api_key(texts, "RETRIEVAL_DOCUMENT")
    else:
        client = get_genai_client()
        response = client.models.embed_content(
            model=settings.embedding_model,        # "text-embedding-005"
            contents=texts,
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dimensions,  # 768
                task_type="RETRIEVAL_DOCUMENT",     # <-- document task type
            ),
        )
        vectors = [list(e.values) for e in response.embeddings]
    return vectors
```

Notice the key differences:

1. **Task type**: `RETRIEVAL_QUERY` for queries, `RETRIEVAL_DOCUMENT` for documents
2. **Batch vs single**: `embed_text` handles one string, `embed_batch` handles a list
3. **When called**: `embed_text` is called at search time (latency-sensitive), `embed_batch` is called at ingestion time (throughput-sensitive)

---

## 3. Embedding Model Selection

Choosing an embedding model is one of the most consequential decisions in a RAG system. The model determines the quality of your retrieval, which directly determines the quality of the generated answers. A poor embedding model means the right documents are never found, and no amount of prompt engineering on the generation side will fix that.

---

### MTEB Benchmarks

The **Massive Text Embedding Benchmark (MTEB)** is the standard evaluation suite for embedding models. It tests models across multiple tasks: retrieval, classification, clustering, semantic similarity, and more.

For RAG systems, the most relevant MTEB subtask is **Retrieval** — specifically the NDCG@10 metric (Normalized Discounted Cumulative Gain at rank 10), which measures how well the top-10 retrieved results match the ground truth relevant documents.

```
MTEB RETRIEVAL LEADERBOARD (representative scores, approximate):

Model                      | Dims  | NDCG@10 | Provider
---------------------------|-------|---------|----------
text-embedding-005         | 768   | ~0.72   | Google
text-embedding-3-large     | 3072  | ~0.71   | OpenAI
text-embedding-3-small     | 1536  | ~0.66   | OpenAI
embed-v4.0                 | 1024  | ~0.70   | Cohere
text-embedding-ada-002     | 1536  | ~0.63   | OpenAI
voyage-3                   | 1024  | ~0.71   | Voyage AI

Note: Scores vary by specific retrieval benchmark subset.
Check the MTEB leaderboard for current rankings.
```

The leaderboard changes frequently as new models are released. The key insight is not to chase the top spot but to understand the tradeoffs.

---

### Dimension Tradeoffs

Embedding dimensions determine the size of the vector that represents each piece of text. More dimensions can capture more nuance, but at a cost:

| Dimensions | Storage per Vector | Index Memory | Search Speed | Quality |
|------------|-------------------|--------------|--------------|---------|
| 256 | 1 KB | Low | Fast | Noticeable quality loss |
| 768 | 3 KB | Moderate | Good | Strong retrieval quality |
| 1024 | 4 KB | Moderate-High | Good | Slightly better than 768 |
| 1536 | 6 KB | High | Slower | Diminishing returns |
| 3072 | 12 KB | Very High | Slowest | Marginal improvement |

The relationship between dimensions and quality is **not linear**. Going from 256 to 768 dimensions produces a significant quality jump. Going from 768 to 3072 produces a much smaller improvement — often less than 2% on MTEB retrieval benchmarks — while quadrupling storage and slowing search.

```
QUALITY vs DIMENSIONS (conceptual):

Quality
  │
  │                            ● 3072 dims
  │                      ● 1536 dims
  │                  ● 1024 dims
  │             ● 768 dims     ← sweet spot for most use cases
  │
  │        ● 512 dims
  │
  │   ● 256 dims
  │
  └──────────────────────────────────→ Dimensions
        256   512   768  1024  1536  3072

  The curve flattens quickly. Doubling dimensions from 768 to 1536
  gives much less improvement than going from 256 to 512.
```

```
AI DOCTOR EXAMPLE:
Our project uses 768 dimensions. For a clinical guidelines collection
of ~1,000 document chunks, the total vector storage is approximately:

  1,000 chunks x 768 dimensions x 4 bytes/float = ~3 MB

This is trivial. Even at 100,000 chunks, we would use ~300 MB — well
within a single Qdrant container's memory. The 768-dimension choice
gives us strong retrieval quality without overprovisioning storage
for our dataset size.
```

---

### Why We Chose text-embedding-005

The project's configuration in `backend/src/config.py`:

```python
# backend/src/config.py
embedding_model: str = "text-embedding-005"
embedding_dimensions: int = 768
```

The decision was based on several factors:

1. **Retrieval quality**: text-embedding-005 scores competitively on MTEB retrieval benchmarks, particularly on medical and scientific text subsets
2. **Asymmetric task types**: Supports RETRIEVAL_QUERY / RETRIEVAL_DOCUMENT distinction, which improves retrieval quality for RAG
3. **768 dimensions**: A good balance of quality and efficiency for our dataset size
4. **Matryoshka representation**: text-embedding-005 supports output dimensionality truncation — you can request 768 dims from a model that natively produces higher-dimensional vectors, and the first 768 dims retain most of the quality
5. **Vertex AI integration**: Runs on Google Cloud infrastructure, which the project already uses. Supports both API key and ADC authentication
6. **Cost**: Competitive pricing for batch embedding operations

---

### Alternative Models

Other embedding models worth knowing about:

**OpenAI text-embedding-3-small / 3-large**
- 1536 / 3072 dimensions (also support Matryoshka truncation)
- Good quality, widely used
- Requires OpenAI API key (separate vendor from our Google Cloud setup)

**Cohere embed-v4.0**
- 1024 dimensions
- Strong multilingual support
- Native int8/binary quantization for compressed storage

**Voyage AI voyage-3**
- 1024 dimensions
- Specifically strong on code and technical text
- Good option for codebases and documentation

**Open-source options (BGE, E5, GTE)**
- Can be self-hosted (no API dependency)
- Competitive quality on MTEB
- Require GPU infrastructure for reasonable throughput

For the AI Doctor project, the vendor alignment with Google Cloud and the task type support made text-embedding-005 the pragmatic choice. If you are building a similar system on a different cloud provider, pick the embedding model that integrates cleanly with your existing infrastructure. The quality differences between top-tier models are small compared to the impact of chunking strategy, retrieval pipeline design, and prompt engineering.

---

## 4. Vector Similarity and Distance Metrics

Once you have vectors, you need a way to measure how "close" two vectors are. This is where distance metrics come in. The choice of metric affects search results, and it must match how the embedding model was trained.

---

### Cosine Similarity

**Cosine similarity** measures the angle between two vectors, ignoring their magnitude. It is the most commonly used metric for text embeddings.

```
COSINE SIMILARITY FORMULA:

              A · B           Σ(Ai × Bi)
cos(θ) = ─────────── = ──────────────────────
           |A| × |B|    √Σ(Ai²) × √Σ(Bi²)

Range: -1 to +1
  +1  = identical direction (maximum similarity)
   0  = perpendicular (no similarity)
  -1  = opposite direction (maximum dissimilarity)
```

**Worked example** with small 3-dimensional vectors:

```
Vector A = [1, 2, 3]    (e.g., "heart attack")
Vector B = [2, 4, 6]    (e.g., "myocardial infarction")
Vector C = [3, -1, 0]   (e.g., "pizza recipe")

Cosine(A, B):
  A · B = (1×2) + (2×4) + (3×6) = 2 + 8 + 18 = 28
  |A|   = √(1² + 2² + 3²) = √14 ≈ 3.74
  |B|   = √(2² + 4² + 6²) = √56 ≈ 7.48
  cos(A,B) = 28 / (3.74 × 7.48) = 28 / 27.97 ≈ 1.0

  → Nearly identical! B is A scaled by 2, same direction.

Cosine(A, C):
  A · C = (1×3) + (2×-1) + (3×0) = 3 - 2 + 0 = 1
  |A|   = √14 ≈ 3.74
  |C|   = √(9 + 1 + 0) = √10 ≈ 3.16
  cos(A,C) = 1 / (3.74 × 3.16) = 1 / 11.82 ≈ 0.085

  → Very low similarity. Different topics.
```

**Why cosine works for text embeddings**: Most embedding models produce vectors where magnitude varies with text length or complexity, but direction captures meaning. Cosine similarity ignores magnitude and focuses on direction, which makes it robust to these variations.

---

### Dot Product

The **dot product** (inner product) multiplies corresponding elements and sums the results:

```
DOT PRODUCT:

A · B = Σ(Ai × Bi)

Range: -∞ to +∞ (unbounded)
```

The dot product is equivalent to cosine similarity **when vectors are normalized** (length = 1):

```
If |A| = 1 and |B| = 1:
  A · B = cos(θ) × |A| × |B| = cos(θ) × 1 × 1 = cos(θ)
```

Many embedding models produce normalized vectors, which means cosine similarity and dot product give the same ranking. Dot product is computationally cheaper (no need to compute magnitudes), so if your vectors are normalized, dot product is the better choice for performance.

---

### L2 / Euclidean Distance

**Euclidean distance** (L2 distance) measures the straight-line distance between two points:

```
L2 DISTANCE:

d(A, B) = √Σ(Ai - Bi)²

Range: 0 to +∞
  0 = identical vectors
  ∞ = maximally different
```

Note that L2 is a distance (lower is better), while cosine similarity is a similarity (higher is better). For normalized vectors, L2 distance and cosine similarity are monotonically related:

```
L2²(A, B) = 2 - 2 × cos(A, B)    (when |A| = |B| = 1)

So minimizing L2 distance is equivalent to maximizing cosine similarity
for normalized vectors.
```

L2 is more commonly used in computer vision (image embeddings) than in text retrieval.

---

### Which Metric to Use

| Metric | When to Use | Pros | Cons |
|--------|-------------|------|------|
| **Cosine** | Default for text embeddings | Robust to magnitude variation | Slightly slower than dot product |
| **Dot Product** | Normalized vectors | Fastest computation | Sensitive to magnitude if not normalized |
| **L2 / Euclidean** | Image embeddings, some clustering | Intuitive geometric interpretation | Sensitive to magnitude |

```
AI DOCTOR EXAMPLE:
Our Qdrant collection is configured with Distance.COSINE:

  VectorParams(
      size=768,                # embedding dimensions
      distance=Distance.COSINE  # cosine similarity metric
  )

This is the safe default. Google's text-embedding-005 produces
vectors that work well with cosine similarity. The retrieval
results are scored from 0 to 1, where 1 means identical.
```

---

### Visualizing Similarity in 2D

Real embedding vectors have 768 dimensions. We cannot visualize 768-dimensional space, but 2D projections help build intuition for how vector similarity works:

```
COSINE SIMILARITY IN 2D:

  Y
  │      B ●
  │       /          cos(A,B) ≈ 0.95  (small angle = high similarity)
  │      / ╱ angle θ₁
  │     / ╱
  │    ●─────────→ A
  │
  │
  │                  cos(A,C) ≈ 0.10  (large angle = low similarity)
  │
  │               angle θ₂
  │        ╲
  │         ╲
  │          ● C
  │
  └──────────────────────── X


  Key insight: cosine similarity depends on DIRECTION, not LENGTH.

  D = [0.1, 0.2]  and  E = [100, 200]
  have cos(D,E) = 1.0 — they point the same direction.

  This is why cosine works for text: a short phrase and a long
  paragraph can describe the same concept. Their embedding
  magnitudes differ, but their directions align.
```

```
VECTOR SEARCH AS "FIND THE CLOSEST DIRECTION":

                            ● doc_3 (diabetes management)
                           /
                          /
  ● doc_5              /
  (unrelated)        /
                   /
                  query ●──────────→ ● doc_1 (closest match!)
                        ╲
                         ╲
                          ● doc_2 (second closest)
                           ╲
                            ╲
                             ● doc_4 (moderate match)

  The vector database finds the K nearest neighbors to
  the query vector. In this case, doc_1 and doc_2 are
  the most relevant results.
```

---

## 5. Vector Database Architecture

### Why Not Just Use SQL?

You could store embedding vectors in a regular database. PostgreSQL with pgvector does exactly this. For a query, you would compute the cosine similarity between the query vector and every stored vector, then sort by similarity. This is **exact nearest neighbor search** — it guarantees finding the truly closest vectors.

The problem is performance. Exact search is O(N) — it must scan every vector:

```
EXACT SEARCH SCALING:

  Vectors        Comparisons        Time (768-dim, single CPU)
  ──────────────────────────────────────────────────────────
  1,000          1,000              ~1 ms
  10,000         10,000             ~10 ms
  100,000        100,000            ~100 ms
  1,000,000      1,000,000          ~1 sec
  10,000,000     10,000,000         ~10 sec
  100,000,000    100,000,000        ~100 sec   ← unusable for search

  Each comparison: 768 multiplications + 768 additions + sqrt
  ≈ ~1,500 floating-point operations per comparison
```

For the AI Doctor's ~1,000 clinical guideline chunks, exact search is fine — 1 ms is imperceptible. But if the project grows to millions of chunks (multiple hospitals, all guidelines ever published, research papers), exact search becomes a bottleneck.

This is where **Approximate Nearest Neighbor (ANN)** algorithms come in.

---

### Approximate Nearest Neighbors (ANN)

ANN algorithms trade a small amount of accuracy for a massive speedup. Instead of checking every vector, they build a data structure that allows quickly navigating to the approximate neighborhood of the query vector.

```
EXACT vs APPROXIMATE SEARCH:

  Exact Search (brute force):
  ┌───────────────────────────────────────────┐
  │ Check EVERY point. Guaranteed correct.     │
  │ O(N) comparisons.                          │
  │                                            │
  │  query ●                                   │
  │         ╲ compare with ALL vectors          │
  │          ╲                                  │
  │    ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ● ●  │
  │    (scan every single one)                 │
  └───────────────────────────────────────────┘
  Time: O(N)  |  Recall: 100%

  Approximate Search (HNSW):
  ┌───────────────────────────────────────────┐
  │ Navigate a graph. Skip most points.        │
  │ O(log N) comparisons.                      │
  │                                            │
  │  query ●──→ ●──→ ●──→ ● (found!)          │
  │              │         │                   │
  │              ▼         ▼                   │
  │              ●    ● ● ●                    │
  │    (most points never checked)             │
  └───────────────────────────────────────────┘
  Time: O(log N)  |  Recall: ~95-99%
```

The "approximate" part means the algorithm might miss the absolute nearest neighbor, returning the second or third nearest instead. In practice, recall rates of 95-99% are achievable, meaning 95-99% of the time the true nearest neighbor is in the returned results. For search applications, this is more than acceptable — the difference between the best match and the second-best match is usually negligible.

---

### HNSW — The Algorithm Behind Modern Vector Search

**Hierarchical Navigable Small World (HNSW)** is the dominant ANN algorithm used by Qdrant, Weaviate, pgvector (as of v0.7.0+), and many other vector databases. Understanding HNSW at a conceptual level helps you tune its parameters.

**The core idea**: Build a multi-layer graph where:
- The **top layer** has very few nodes, spread far apart (like a highway system)
- Each **lower layer** has more nodes, more densely connected (like local roads)
- The **bottom layer** has ALL nodes with dense local connections (like neighborhood streets)

Search starts at the top layer and works down, getting more precise at each level.

```
HNSW MULTI-LAYER STRUCTURE:

Layer 2 (sparse — "highways"):
    A ●───────────────────────────────● E
    │                                 │
    │  (few nodes, long-range links)  │
    │                                 │

Layer 1 (medium — "main roads"):
    A ●────────● C ────────● E
    │          │           │
    ●B         ●D          ●F
    (more nodes, medium-range links)

Layer 0 (dense — "local streets"):
    A●─●B─●─●─●C─●─●D─●─●─●E─●─●F
     │ │ │ │ │ │ │ │ │ │ │ │ │ │
     ●─●─●─●─●─●─●─●─●─●─●─●─●─●
    (ALL nodes, short-range links)
```

**Search process** — finding the nearest neighbor of a query vector Q:

```
HNSW SEARCH WALKTHROUGH:

Step 1: Enter at Layer 2 (sparse)
         Start at node A. Compare Q to A and E.
         E is closer to Q. Move to E.

         A ●─────────────────────● E ← (current position)

Step 2: Drop to Layer 1, starting at E
         Compare Q to E's neighbors: C, F
         F is closest. Move to F.

         A ●────● C ────● E
                          │
                          ● F ← (current position)

Step 3: Drop to Layer 0, starting at F
         Compare Q to F's local neighbors.
         Find that node G (next to F) is the closest.

         ...─● E ─●─● F ─● G ─●─...
                              ↑
                         closest neighbor!

Step 4: Return G as the approximate nearest neighbor.

Total comparisons: ~20 (instead of scanning all N vectors)
```

**HNSW parameters** that matter:

| Parameter | What It Controls | Higher Value Means |
|-----------|-----------------|-------------------|
| `M` | Connections per node | Better recall, more memory, slower indexing |
| `ef_construction` | Search width during index building | Better recall, slower indexing |
| `ef` | Search width during query | Better recall, slower queries |

For most applications, the defaults work well. Qdrant's defaults (M=16, ef_construction=100) provide good recall with reasonable performance.

---

### Vector Database Comparison

| Feature | **Qdrant** | **pgvector** | **Pinecone** | **Weaviate** | **Chroma** |
|---------|-----------|-------------|-------------|-------------|-----------|
| **Type** | Standalone | PostgreSQL extension | Managed service | Standalone | Embedded |
| **ANN Algorithm** | HNSW | HNSW (IVFFlat also) | Proprietary | HNSW | Brute force / HNSW |
| **Filtering** | Native payload filters | SQL WHERE clauses | Metadata filters | GraphQL + filters | Metadata filters |
| **Deployment** | Docker / Cloud | Existing PostgreSQL | Fully managed (SaaS) | Docker / Cloud | In-process (pip install) |
| **Scaling** | Horizontal sharding | Limited by PostgreSQL | Automatic | Horizontal sharding | Single-node |
| **Language** | Rust | C | Unknown (SaaS) | Go | Python |
| **Best For** | Production RAG, filtering-heavy | Small datasets, existing PG | Zero-ops, managed | Knowledge graphs | Prototyping, small projects |
| **Docker** | Yes | N/A (PG extension) | No (SaaS only) | Yes | No (pip install) |

**When to use each:**

- **Qdrant**: You need payload filtering (filter by specialty, document type), good Docker story, and want to own your data. This is our choice.
- **pgvector**: You already have PostgreSQL, your dataset is under ~100K vectors, and you want to avoid adding another service.
- **Pinecone**: You want zero operations overhead, are willing to pay for a managed service, and do not need to self-host.
- **Weaviate**: You need object-level semantic search with complex schema relationships (more of a knowledge graph + vector store hybrid).
- **Chroma**: You are prototyping, need something running in 5 minutes, and your dataset fits in memory on a single machine.

---

## 6. Qdrant — Our Vector Store

### Why Qdrant

The AI Doctor project uses Qdrant for several reasons:

1. **Payload filtering**: Clinical guidelines have metadata (specialty, document type, conditions, drugs). Qdrant's native payload filtering lets us search within a specialty without post-filtering.
2. **Docker-native**: Single container, easy to run locally and in CI/CD.
3. **Rust performance**: HNSW implementation in Rust gives excellent search latency.
4. **Cosine distance**: First-class support for the metric our embedding model is optimized for.
5. **In-memory mode**: `QdrantClient(":memory:")` for unit tests — no Docker needed in CI.
6. **gRPC + REST**: Both fast binary protocol (gRPC on port 6334) and developer-friendly REST (port 6333).

---

### Core Concepts

Qdrant organizes data into three layers:

```
QDRANT DATA MODEL:

Collection: "clinical_guidelines"
├── Vector Config: 768 dims, cosine distance
├── Payload Indexes: specialty, document_type, conditions, drugs
│
├── Point (id: uuid-1)
│   ├── Vector: [0.12, -0.34, ..., 0.56]  (768 floats)
│   └── Payload: {
│         "text": "Management of atrial fibrillation...",
│         "document_id": "afib-guidelines-2024",
│         "document_title": "AHA AF Management Guidelines",
│         "section_path": "Rate Control > Beta Blockers",
│         "specialty": "cardiology",
│         "document_type": "clinical_guideline",
│         "conditions": ["atrial_fibrillation"],
│         "drugs": ["metoprolol", "diltiazem"],
│         "chunk_index": 3,
│         "total_chunks": 24
│       }
│
├── Point (id: uuid-2)
│   ├── Vector: [0.45, 0.23, ..., -0.12]
│   └── Payload: { ... }
│
└── ... (more points)
```

| Concept | What It Is | Analogy |
|---------|-----------|---------|
| **Collection** | A named group of vectors with the same dimensionality | A database table |
| **Point** | One vector + its metadata (payload) | A table row |
| **Vector** | The embedding (list of floats) | The searchable column |
| **Payload** | Arbitrary JSON metadata stored with the vector | Other columns |
| **Payload Index** | An index on a payload field for fast filtering | A database index |

---

### Docker Setup

The Qdrant container runs alongside PostgreSQL in our docker-compose:

```yaml
# docker-compose.yml

qdrant:
  image: qdrant/qdrant:v1.12.1
  container_name: build_ai_agents_qdrant
  ports:
    - "6333:6333"    # REST API
    - "6334:6334"    # gRPC API
  volumes:
    - qdrant_data:/qdrant/storage
  restart: unless-stopped

volumes:
  qdrant_data:       # Persists vectors across container restarts
```

Two ports are exposed:
- **6333**: REST API — used by the Python client for convenience and debugging
- **6334**: gRPC API — used for production workloads (faster binary protocol)

The `qdrant_data` volume ensures that indexed vectors survive container restarts. Without it, you would need to re-embed and re-index every time the container restarts.

---

### Collection Creation

The `ensure_collection()` function creates the collection and its payload indexes if they do not exist:

```python
# backend/src/services/rag_service.py

def ensure_collection() -> None:
    """Create the Qdrant collection if it doesn't exist."""
    client = get_qdrant_client()
    collections = [c.name for c in client.get_collections().collections]

    if settings.qdrant_collection not in collections:
        # Create collection with vector configuration
        client.create_collection(
            collection_name=settings.qdrant_collection,   # "clinical_guidelines"
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,        # 768
                distance=Distance.COSINE,                  # cosine similarity
            ),
        )

        # Create payload indexes for filtered search
        for field, schema_type in [
            ("document_id", PayloadSchemaType.KEYWORD),
            ("specialty", PayloadSchemaType.KEYWORD),
            ("document_type", PayloadSchemaType.KEYWORD),
            ("conditions", PayloadSchemaType.KEYWORD),
            ("drugs", PayloadSchemaType.KEYWORD),
        ]:
            client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=schema_type,
            )
```

This function is **idempotent** — calling it multiple times is safe. If the collection already exists, it skips creation. This is important for application startup: the backend calls `ensure_collection()` during initialization, and it works whether this is a fresh deployment or a restart.

```
COLLECTION CREATION FLOW:

  Application Startup
        │
        ▼
  ensure_collection()
        │
        ▼
  ┌─────────────────────────┐
  │ Does collection exist?   │
  └─────────┬───────────────┘
            │
      ┌─────┴─────┐
      │           │
     Yes          No
      │           │
      ▼           ▼
   (skip)    Create collection
              (768 dims, cosine)
                  │
                  ▼
             Create payload indexes
              (specialty, document_type,
               conditions, drugs, document_id)
                  │
                  ▼
              Ready for upserts
```

---

### Payload Indexes and Filtered Search

**Payload indexes** are what make Qdrant powerful for our use case. Without them, filtering happens *after* vector search — Qdrant would find the K nearest vectors, then throw away any that do not match the filter. With payload indexes, filtering happens *during* search — Qdrant only considers vectors that match the filter.

```
WITHOUT PAYLOAD INDEX (post-filtering):

  1. Find 100 nearest vectors to query
  2. Filter: keep only specialty="cardiology"
  3. Result: maybe 3 cardiology results out of 100
     (wasteful — searched 97 irrelevant vectors)

WITH PAYLOAD INDEX (pre-filtering):

  1. Restrict search space to specialty="cardiology" vectors
  2. Find 5 nearest vectors within that subset
  3. Result: 5 cardiology results
     (efficient — only searched relevant vectors)
```

The search implementation from our codebase:

```python
# backend/src/services/rag_service.py

def search(
    query: str,
    specialty: str | None = None,
    limit: int = 5,
) -> list[RetrievalResult]:
    """Embed query, search Qdrant, return scored results."""
    query_vector = embed_text(query)  # RETRIEVAL_QUERY task type

    # Build optional filter
    must_conditions = []
    if specialty:
        must_conditions.append(
            FieldCondition(key="specialty", match=MatchValue(value=specialty))
        )
    query_filter = Filter(must=must_conditions) if must_conditions else None

    client = get_qdrant_client()
    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=query_filter,       # <-- payload filter
        score_threshold=0.5,             # minimum similarity score
        limit=limit,                     # max results
        with_payload=True,               # return metadata
    )

    # Convert Qdrant points to our domain model
    retrieval_results = []
    for idx, point in enumerate(results.points):
        payload = point.payload
        chunk = DocumentChunk(
            text=payload["text"],
            document_id=payload["document_id"],
            document_title=payload["document_title"],
            section_path=payload["section_path"],
            specialty=payload["specialty"],
            # ... remaining fields
        )
        retrieval_results.append(
            RetrievalResult(chunk=chunk, score=point.score, source_id=idx + 1)
        )

    return retrieval_results
```

```
AI DOCTOR EXAMPLE:
When generating a briefing for a cardiology patient, the agent searches
with specialty="cardiology". This filters out endocrinology guidelines,
oncology guidelines, and everything else — the search only considers
cardiology documents.

Without this filter, a search for "rate control medication" might
return results about gastric motility drugs (which also involve
"rate control" in a different context). The specialty filter
eliminates this cross-domain noise.

The five payload indexes in our collection:
  - document_id   → find all chunks of a specific document
  - specialty     → filter by medical specialty
  - document_type → filter by guideline vs. protocol vs. reference
  - conditions    → filter by disease/condition
  - drugs         → filter by medication name
```

---

### Search Implementation

The complete search flow ties together embeddings, vector search, and payload filtering:

```
COMPLETE SEARCH FLOW:

  Physician's question: "What's the target heart rate for
                         rate-controlled atrial fibrillation?"

  ┌──────────────────────────────────────────────────────┐
  │ Step 1: Embed the query                               │
  │                                                       │
  │   embed_text("What's the target heart rate...")       │
  │   task_type = "RETRIEVAL_QUERY"                       │
  │                                                       │
  │   → [0.12, -0.34, 0.56, ..., 0.23]  (768 dims)      │
  └───────────────────────┬──────────────────────────────┘
                          │
                          ▼
  ┌──────────────────────────────────────────────────────┐
  │ Step 2: Build filter (if specialty provided)          │
  │                                                       │
  │   specialty = "cardiology"                            │
  │   filter = Filter(must=[                              │
  │     FieldCondition(key="specialty",                   │
  │                    match=MatchValue("cardiology"))    │
  │   ])                                                  │
  └───────────────────────┬──────────────────────────────┘
                          │
                          ▼
  ┌──────────────────────────────────────────────────────┐
  │ Step 3: Query Qdrant                                  │
  │                                                       │
  │   client.query_points(                                │
  │     collection = "clinical_guidelines"                │
  │     query = [0.12, -0.34, ...]                        │
  │     filter = specialty == "cardiology"                │
  │     score_threshold = 0.5                             │
  │     limit = 5                                         │
  │   )                                                   │
  └───────────────────────┬──────────────────────────────┘
                          │
                          ▼
  ┌──────────────────────────────────────────────────────┐
  │ Step 4: Return ranked results                         │
  │                                                       │
  │   1. "AHA AF Guidelines > Rate Control > Targets"     │
  │      score: 0.91, specialty: cardiology               │
  │                                                       │
  │   2. "ESC AF Guidelines > Ventricular Rate"           │
  │      score: 0.87, specialty: cardiology               │
  │                                                       │
  │   3. "Rate vs Rhythm Control Comparison"              │
  │      score: 0.82, specialty: cardiology               │
  └──────────────────────────────────────────────────────┘
```

The results are then formatted as XML and passed to the Claude agent as context for generation. That formatting happens in `format_as_xml_sources()`:

```python
# backend/src/services/rag_service.py

def format_as_xml_sources(results: list[RetrievalResult]) -> str:
    """Format retrieval results as XML for agent consumption."""
    if not results:
        return "<clinical_guidelines>No relevant guidelines found.</clinical_guidelines>"

    lines = ["<clinical_guidelines>"]
    for r in results:
        lines.append(
            f'  <source id="{r.source_id}" '
            f'document="{r.chunk.document_title}" '
            f'section="{r.chunk.section_path}" '
            f'score="{r.score:.2f}">'
        )
        lines.append(f"    {r.chunk.text}")
        lines.append("  </source>")
    lines.append("</clinical_guidelines>")
    return "\n".join(lines)
```

This XML format is consumed by the Claude agent's system prompt, which instructs it to cite sources by ID. But that is the topic of the next document — RAG Architecture and Pipeline.

---

## 7. Indexing and Performance

### Deterministic IDs with UUID5

When you upsert a vector into Qdrant, it needs a unique ID. You have two choices: let the database generate a random ID, or provide a deterministic one.

We use **UUID5** — a deterministic UUID generated from a namespace and a name string:

```python
# backend/src/services/rag_service.py

def upsert_chunks(chunks: list[DocumentChunk], vectors: list[list[float]]) -> None:
    """Upsert document chunks with their embedding vectors into Qdrant."""
    client = get_qdrant_client()
    points = [
        PointStruct(
            id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_DNS,
                    f"{chunk.document_id}:{chunk.chunk_index}"
                )
            ),
            vector=vector,
            payload={
                "text": chunk.text,
                "document_id": chunk.document_id,
                "document_title": chunk.document_title,
                "section_path": chunk.section_path,
                "specialty": chunk.specialty,
                "document_type": chunk.document_type,
                "conditions": chunk.conditions,
                "drugs": chunk.drugs,
                "publication_date": chunk.publication_date.isoformat(),
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)
```

The UUID5 is generated from `f"{chunk.document_id}:{chunk.chunk_index}"`. This means:

```
DETERMINISTIC ID GENERATION:

  Input: document_id="afib-guidelines-2024", chunk_index=3
  Name string: "afib-guidelines-2024:3"
  UUID5: uuid5(NAMESPACE_DNS, "afib-guidelines-2024:3")
       = "a7f2c3d1-..." (always the same for this input)

  Same document + same chunk index → same UUID → same ID every time
```

---

### Idempotent Upserts

Deterministic IDs enable **idempotent upserts**. "Upsert" means "insert or update" — if the ID already exists, the vector and payload are overwritten. Combined with UUID5:

```
IDEMPOTENT UPSERT FLOW:

First ingestion of "afib-guidelines-2024":
  chunk 0 → uuid5("afib-guidelines-2024:0") → INSERT (new point)
  chunk 1 → uuid5("afib-guidelines-2024:1") → INSERT (new point)
  chunk 2 → uuid5("afib-guidelines-2024:2") → INSERT (new point)

Re-ingestion of same document (e.g., pipeline rerun):
  chunk 0 → uuid5("afib-guidelines-2024:0") → UPDATE (same ID, overwrites)
  chunk 1 → uuid5("afib-guidelines-2024:1") → UPDATE (same ID, overwrites)
  chunk 2 → uuid5("afib-guidelines-2024:2") → UPDATE (same ID, overwrites)

Result: No duplicates. The collection has exactly 3 chunks for this
document, regardless of how many times the ingestion pipeline runs.
```

```
AI DOCTOR EXAMPLE:
Without deterministic IDs, re-running the ingestion script would
create duplicate chunks. A search for "AFib rate control" might
return the same paragraph 5 times (once per pipeline run). The
physician sees redundant results, and the Claude agent receives
duplicated context — wasting tokens and degrading answer quality.

UUID5 guarantees that re-ingesting "AHA AF Guidelines 2024" always
produces the same set of IDs. The upsert overwrites existing vectors
(which may be identical anyway), and the collection stays clean.

This is particularly important during development: you often re-run
the ingestion script after changing chunking parameters, and you
want a clean slate without manually deleting the collection.
```

---

### In-Memory Qdrant for Testing

Running a full Qdrant Docker container for unit tests is slow and fragile. The Qdrant Python client supports an in-memory mode that runs entirely within the test process:

```python
# backend/tests/test_rag_service.py

@pytest.fixture
def in_memory_qdrant(monkeypatch: pytest.MonkeyPatch) -> QdrantClient:
    """Use in-memory Qdrant for tests."""
    client = QdrantClient(":memory:")
    monkeypatch.setattr(rag_service, "_qdrant_client", client)
    monkeypatch.setattr(rag_service, "get_qdrant_client", lambda: client)
    return client
```

This pattern has several advantages:

| Approach | Startup Time | Docker Required | Isolation | CI/CD Friendly |
|----------|-------------|-----------------|-----------|----------------|
| Docker Qdrant | ~2-3 sec | Yes | Container-level | Needs Docker-in-Docker |
| In-memory Qdrant | ~10 ms | No | Process-level | Works everywhere |

The in-memory client supports the full Qdrant API — collection creation, upserts, search, filtering. The only difference is that data is lost when the test process exits. This is exactly what you want for tests: a fresh database for each test, with zero setup overhead.

```
TEST ARCHITECTURE:

  pytest process
  ┌──────────────────────────────────────────┐
  │                                           │
  │  test_search_returns_relevant_results()   │
  │     │                                     │
  │     ▼                                     │
  │  in_memory_qdrant fixture                 │
  │     │                                     │
  │     ▼                                     │
  │  QdrantClient(":memory:")                 │
  │     │                                     │
  │     ├── ensure_collection()               │
  │     ├── upsert_chunks(test_data)          │
  │     ├── search("test query")              │
  │     └── assert results match expected     │
  │                                           │
  │  (Qdrant state is garbage-collected       │
  │   when test finishes — no cleanup needed) │
  └──────────────────────────────────────────┘

  No Docker. No network calls. No cleanup.
  Runs in CI with just `uv run pytest`.
```

---

### Score Thresholds

Our search uses a `score_threshold=0.5`:

```python
results = client.query_points(
    collection_name=settings.qdrant_collection,
    query=query_vector,
    query_filter=query_filter,
    score_threshold=0.5,      # <-- minimum cosine similarity
    limit=limit,
    with_payload=True,
)
```

This means Qdrant will not return any results with cosine similarity below 0.5. Why?

```
SCORE THRESHOLD REASONING:

  Score Range    | Interpretation                    | Action
  ─────────────────────────────────────────────────────────────
  0.85 - 1.00   | Highly relevant, near-exact match | Include (confident)
  0.70 - 0.85   | Strongly relevant                 | Include
  0.50 - 0.70   | Moderately relevant               | Include (borderline)
  0.30 - 0.50   | Weak relevance, possibly noise     | Exclude
  0.00 - 0.30   | Not relevant                       | Exclude

  Setting threshold=0.5 filters out noise while allowing
  moderately relevant results through. The agent can then
  decide which results to actually cite.
```

The threshold value of 0.5 is a starting point. In practice, you tune this based on your data:

- Too high (e.g., 0.8): Misses relevant results that use different terminology
- Too low (e.g., 0.2): Returns irrelevant noise that confuses the agent
- Just right (0.4-0.6): Captures relevant results while filtering noise

```
AI DOCTOR EXAMPLE:
If a physician asks about "blood pressure management in pregnancy"
and the collection contains a chunk about "antihypertensive therapy
in gestational hypertension," the cosine similarity might be 0.72
— above our threshold. The chunk is returned and cited.

A chunk about "blood bank management procedures" might score 0.35
— below the threshold. It is filtered out, even though it contains
the word "blood."

This is semantic search in action: the threshold operates on
meaning-similarity, not keyword overlap.
```

---

### Batch Embedding Performance

Embedding text is the most time-consuming part of the ingestion pipeline. The Vertex AI embedding API supports batch operations, which significantly reduces overhead:

```
SINGLE vs BATCH EMBEDDING:

  Single (one API call per chunk):
  ┌────────┐  →  API  →  ┌────────┐  →  API  →  ┌────────┐  →  API
  │chunk 1 │              │chunk 2 │              │chunk 3 │
  └────────┘              └────────┘              └────────┘
  Time: N × (network_latency + compute)

  Batch (one API call for all chunks):
  ┌────────┬────────┬────────┐  →  API (single call)
  │chunk 1 │chunk 2 │chunk 3 │
  └────────┴────────┴────────┘
  Time: 1 × network_latency + N × compute

  For 100 chunks:
    Single: ~100 × 200ms = 20 seconds
    Batch:  ~1 × 200ms + 100 × 5ms = 700ms
```

Our `embed_batch()` function sends all texts in a single API call. For large document ingestion (hundreds of chunks), this reduces embedding time from minutes to seconds.

The Vertex AI API has limits on batch size (typically 250 texts per call). For larger ingestion jobs, the texts would need to be chunked into batches — but for our clinical guidelines collection, a single batch call per document is usually sufficient.

---

### Putting It All Together

Here is the complete data flow from raw clinical guideline to searchable vector:

```
COMPLETE INGESTION + SEARCH PIPELINE:

INGESTION (offline, one-time per document):

  Clinical Guideline (Markdown)
        │
        ▼
  Document Processor              ← document_processor.py
  (parse markdown, split into chunks)
        │
        ▼
  List[DocumentChunk]
  (text + metadata: specialty, conditions, drugs, etc.)
        │
        ▼
  embed_batch(chunk_texts)        ← rag_service.py
  task_type = "RETRIEVAL_DOCUMENT"
        │
        ▼
  List[List[float]]  (768-dim vectors)
        │
        ▼
  upsert_chunks(chunks, vectors)  ← rag_service.py
  UUID5 deterministic IDs
        │
        ▼
  Qdrant Collection: "clinical_guidelines"


SEARCH (real-time, per patient briefing):

  Agent calls search_clinical_guidelines tool
        │
        ▼
  search(query="...", specialty="cardiology")  ← rag_service.py
        │
        ├─→ embed_text(query)
        │   task_type = "RETRIEVAL_QUERY"
        │   → query_vector (768 dims)
        │
        ├─→ Build filter (specialty="cardiology")
        │
        └─→ client.query_points(
              query=query_vector,
              filter=specialty_filter,
              score_threshold=0.5,
              limit=5
            )
              │
              ▼
        List[RetrievalResult]
        (chunks + scores, ranked by similarity)
              │
              ▼
        format_as_xml_sources(results)
              │
              ▼
        XML string → fed to Claude agent as context
```

---

## Next Steps

> **Next:** Proceed to [05-RAG-ARCHITECTURE-AND-PIPELINE.md](./05-RAG-ARCHITECTURE-AND-PIPELINE.md) to learn how embeddings and vector databases combine into a complete RAG pipeline — from document ingestion through retrieval to agent-augmented generation.

---

*Part 4 of 11: Agent Architecture & AI Model Internals Series*
*AI Doctor Assistant Project*
