# RAG Evaluation and Production

**Part 6 of 11: Agent Architecture & AI Model Internals Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Why RAG Evaluation is Different](#1-why-rag-evaluation-is-different)
2. [Retrieval Quality Metrics](#2-retrieval-quality-metrics)
3. [Testing RAG Systems](#3-testing-rag-systems)
4. [Common Failure Modes and Anti-Patterns](#4-common-failure-modes-and-anti-patterns)
5. [Production Considerations](#5-production-considerations)
6. [Hybrid Search and Advanced Techniques](#6-hybrid-search-and-advanced-techniques)

---

## Learning Objectives

After reading this document, you will be able to:

- Explain why RAG systems require a different evaluation strategy than traditional software -- non-determinism, cascading failures, and the separation of retrieval quality from generation quality
- Calculate retrieval quality metrics (Precision@k, Recall@k, MRR, NDCG) by hand and explain what each measures
- Implement a 5-layer testing strategy that isolates parsing, chunking, embedding, integration, and end-to-end behavior
- Use in-memory Qdrant (`QdrantClient(":memory:")`) to write fast, isolated retrieval tests with no Docker dependency
- Identify the most common RAG failure modes (naive chunking, mixed embeddings, lost-in-the-middle, over-retrieval) and explain the mitigation for each
- Describe production concerns for medical RAG: re-indexing strategies, threshold tuning, latency budgets, document freshness, and monitoring
- Distinguish between dense vector search, BM25 keyword search, hybrid search, and reranking -- and know when each is appropriate

**Key mental models this document builds:**

1. **Retrieval and generation are separate failure surfaces.** You must evaluate them independently. Perfect retrieval with bad generation is fixable (improve the prompt). Bad retrieval with any generation is unfixable (the model reasons over wrong evidence).

2. **RAG testing is layered, not monolithic.** Each layer (parsing, chunking, embedding, search, end-to-end) has its own failure modes. Testing the full pipeline end-to-end without layer isolation is like debugging a 500-line function with no intermediate variables.

3. **Medical RAG has asymmetric error costs.** A false negative (missing a relevant guideline) is dangerous. A false positive (including an irrelevant guideline) is wasteful but safer. This asymmetry drives every threshold and metric decision.

**Common misconceptions this document corrects:**

| Misconception | Reality |
|---------------|---------|
| "If the final answer is good, retrieval must be good" | The model can compensate for bad retrieval using parametric knowledge -- which means it is hallucinating, not citing |
| "More retrieved chunks = better answers" | Over-retrieval dilutes signal and triggers the lost-in-the-middle problem |
| "Vector search always beats keyword search" | Semantic search misses exact medical terms; keyword search misses synonyms. You need both. |
| "RAG tests are flaky because embeddings are non-deterministic" | Mock the embedding layer for unit tests. Test embedding quality separately. |
| "Re-indexing means duplicated documents" | UUID5 deterministic IDs make re-ingestion idempotent |

---

## 1. Why RAG Evaluation is Different

### The Non-Determinism Problem

Traditional software is deterministic. Given the same input, you get the same output. A function that adds two numbers will always return 4 when given 2 and 2. Your tests can assert exact equality.

RAG systems are non-deterministic at multiple levels:

```
┌─────────────────────────────────────────────────────────────────┐
│                   Sources of Non-Determinism                     │
│                                                                  │
│  1. EMBEDDING MODEL                                              │
│     Same text can produce slightly different vectors across       │
│     API calls (floating-point precision, model versioning)        │
│                                                                  │
│  2. VECTOR SEARCH                                                │
│     Approximate nearest neighbor (HNSW) is probabilistic --      │
│     results can vary slightly between searches                    │
│                                                                  │
│  3. CHUNKING CHANGES                                             │
│     Re-chunking a document after an update changes chunk          │
│     boundaries, which changes embeddings, which changes           │
│     what gets retrieved                                          │
│                                                                  │
│  4. LLM GENERATION                                               │
│     Even with temperature=0, the model's response to the         │
│     same retrieved context can vary between calls                 │
│                                                                  │
│  5. INDEX UPDATES                                                │
│     Adding new documents changes what gets retrieved for          │
│     existing queries (new chunks may be closer neighbors)         │
└─────────────────────────────────────────────────────────────────┘
```

This means your tests cannot assert "the answer is exactly this string." They must assert properties: "the answer cites at least one diabetes guideline," "the retrieved chunks contain the metformin dosing section," "the score of the top result exceeds 0.5."

### The Cascading Failure Problem

RAG is a pipeline. Each stage feeds into the next. An error at any stage cascades forward and amplifies:

```
BAD CHUNKING                    BAD EMBEDDINGS
    │                               │
    ▼                               ▼
"Administer 5mg"               Vector for "metformin renal
(which drug? which              dosing" lands far from the
 condition? lost context)       actual metformin chunks
    │                               │
    ▼                               ▼
BAD RETRIEVAL                  BAD RETRIEVAL
    │                               │
    ▼                               ▼
Agent reasons over              Agent reasons over
irrelevant context              wrong context
    │                               │
    ▼                               ▼
BAD GENERATION                 BAD GENERATION
    │                               │
    ▼                               ▼
Wrong clinical advice           Wrong clinical advice
```

This is why you cannot just test the final output. If the final briefing is wrong, you need to know *where* in the pipeline the failure occurred. Was the document parsed incorrectly? Was the chunk boundary wrong? Did the embedding model produce a poor vector? Did the search return irrelevant results? Did the model ignore relevant results?

**Each stage needs its own tests.**

### The Evaluation Split: Retrieval vs. Generation

The fundamental insight of RAG evaluation is that you must evaluate two things independently:

```
┌──────────────────────────────────┬──────────────────────────────────┐
│        RETRIEVAL QUALITY         │        GENERATION QUALITY        │
│                                  │                                  │
│  "Did we find the right          │  "Did the model use the          │
│   documents?"                    │   retrieved context correctly?"  │
│                                  │                                  │
│  Metrics:                        │  Metrics:                        │
│  - Precision@k                   │  - Faithfulness (no halluc.)     │
│  - Recall@k                      │  - Relevance (answers query)     │
│  - MRR                           │  - Citation accuracy             │
│  - NDCG                          │  - Completeness                  │
│                                  │                                  │
│  Ground truth:                   │  Ground truth:                   │
│  Human-labeled query-document    │  Human-reviewed answer quality   │
│  relevance pairs                 │  for given retrieved context     │
│                                  │                                  │
│  Tools:                          │  Tools:                          │
│  - Automated metrics             │  - LLM-as-judge                  │
│  - Deterministic tests           │  - Human evaluation              │
│                                  │  - Rubric-based scoring          │
└──────────────────────────────────┴──────────────────────────────────┘
```

This document focuses primarily on **retrieval quality** -- the metrics and testing strategies for the search component. Generation quality (faithfulness, hallucination detection) is a separate concern that depends on prompt engineering and model capability.

```
AI DOCTOR EXAMPLE:
Consider a patient on metformin with declining eGFR (kidney function).
The agent searches for "metformin renal dosing guidelines."

RETRIEVAL evaluation asks: Did the search return the ADA Standards
chunk about metformin dose adjustment when eGFR < 45?

GENERATION evaluation asks: Given that chunk, did the agent correctly
flag the need for dose adjustment and cite the source?

If retrieval fails, generation has no chance. If retrieval succeeds
but generation fails, that is a prompt engineering problem -- much
easier to fix than a retrieval architecture problem.
```

---

## 2. Retrieval Quality Metrics

### Why Metrics Matter

Without metrics, you are flying blind. "It seems to work" is not an evaluation strategy, especially for medical applications where a missed guideline could mean missed clinical advice.

Retrieval metrics give you concrete numbers:
- **Before a change:** Precision@5 = 0.72, Recall@10 = 0.85
- **After a change:** Precision@5 = 0.68, Recall@10 = 0.81
- **Decision:** The change degraded retrieval quality. Revert.

Without these numbers, you would deploy the change and only discover the regression when a clinician notices a missing guideline in a briefing.

### The Setup: Query, Results, and Relevance

Every retrieval metric starts with the same setup:

1. **A query** -- what the user (or agent) searched for
2. **Retrieved results** -- the k documents returned by the search, in ranked order
3. **Relevance judgments** -- which documents *should* have been returned (ground truth)

For the examples below, we will use this scenario:

```
Query: "metformin renal dosing guidelines"

Our vector store contains 100 chunks from clinical guidelines.
Of those 100, exactly 4 are relevant to this query:

  Relevant chunks (ground truth):
  ┌────────────────────────────────────────────────────────┐
  │  R1: ADA Standards > Metformin > Renal Dosing          │
  │  R2: KDIGO CKD Guidelines > Drug Dosing > Metformin    │
  │  R3: FDA Label: Metformin > Contraindications          │
  │  R4: ADA Standards > Monitoring > Renal Function        │
  └────────────────────────────────────────────────────────┘

Our search returns 5 results (k=5), in this order:

  Position 1: R1  (ADA Metformin Renal Dosing)       ✅ Relevant
  Position 2: X   (Statin therapy guidelines)         ❌ Not relevant
  Position 3: R3  (FDA Metformin Contraindications)   ✅ Relevant
  Position 4: R2  (KDIGO Metformin dosing)            ✅ Relevant
  Position 5: X   (General diabetes overview)         ❌ Not relevant
```

### Precision@k

**What it measures:** Of the k results we returned, how many were actually relevant?

**The question it answers:** "Are we returning garbage alongside the good results?"

**Formula:**

```
                    Number of relevant results in top k
Precision@k  =  ─────────────────────────────────────────
                                  k
```

**Worked example with our data:**

```
Top 5 results:  [R1, X, R3, R2, X]
Relevant:       [✅,  ❌, ✅,  ✅, ❌]

Relevant in top 5 = 3
k = 5

Precision@5 = 3/5 = 0.60
```

**Interpretation:** 60% of the results we showed were relevant. 40% were noise. For a medical system, this means the agent is reasoning over 2 irrelevant chunks alongside 3 relevant ones.

**At different k values:**

```
Precision@1 = 1/1 = 1.00   (top result was relevant -- great!)
Precision@3 = 2/3 = 0.67   (positions 1-3: R1, X, R3 → 2 relevant)
Precision@5 = 3/5 = 0.60   (as computed above)
```

**When to optimize for Precision:** When the cost of showing irrelevant results is high. In our case, irrelevant chunks dilute the agent's context window and can trigger the lost-in-the-middle problem.

### Recall@k

**What it measures:** Of all the relevant documents that exist, how many did we find in our top k?

**The question it answers:** "Are we missing important documents?"

**Formula:**

```
                Number of relevant results in top k
Recall@k  =  ─────────────────────────────────────────
              Total number of relevant documents in corpus
```

**Worked example with our data:**

```
Top 5 results:           [R1, X, R3, R2, X]
Relevant in top 5:       3 (R1, R3, R2)
Total relevant in corpus: 4 (R1, R2, R3, R4)

Recall@5 = 3/4 = 0.75
```

**Interpretation:** We found 75% of the relevant documents. We missed R4 (ADA Standards > Monitoring > Renal Function). In a medical context, that missed chunk might contain critical monitoring frequency information.

**At different k values:**

```
Recall@1 = 1/4 = 0.25   (only found 1 of 4 relevant docs)
Recall@3 = 2/4 = 0.50   (found R1 and R3)
Recall@5 = 3/4 = 0.75   (found R1, R3, R2)
Recall@10 = 4/4 = 1.00  (if R4 appears in positions 6-10)
```

**When to optimize for Recall:** When missing a relevant document is dangerous. For medical RAG, recall is often more important than precision -- it is better to include some noise than to miss a contraindication.

```
AI DOCTOR EXAMPLE:
The project's RAG-ARCH.md sets these targets:
  - precision@5 > 0.6
  - recall@10 > 0.8

Why these specific numbers?

Precision@5 > 0.6 means at least 3 of 5 returned chunks should be
relevant. This keeps the agent's context mostly signal, not noise.

Recall@10 > 0.8 means we find at least 80% of all relevant guidelines
when we look at the top 10 results. This catches most critical
information, even if it requires looking beyond the top 5.

The recall target is set at k=10 (not k=5) because we would rather
cast a wider net and find everything than restrict results and miss
a critical contraindication.
```

### The Precision-Recall Tradeoff

Precision and recall are in tension. Increasing k (returning more results) tends to improve recall but hurt precision:

```
k     Precision@k    Recall@k     Effect
─────────────────────────────────────────────────
1       1.00           0.25      Very precise, misses 75%
3       0.67           0.50      Moderate precision, moderate recall
5       0.60           0.75      Good recall, acceptable precision
10      0.40           1.00      Found everything, but 60% noise
20      0.20           1.00      Terrible precision, recall maxed
```

Visualized:

```
Quality
  │
1.0│ ●─── Precision
  │  \
  │   \            ╱── Recall
  │    \         ╱
  │     \      ╱
0.5│      \   ╱
  │       ╲╱       ← Crossover point
  │      ╱  \
  │    ╱     ───────
  │  ╱
0.0│╱
  └──────────────────── k
    1   3   5   10  20
```

The optimal k depends on your application. For the AI Doctor, we use k=5 as the default with a score threshold of 0.5 to filter out low-quality results. This means we return *up to* 5 results, but fewer if some fall below the threshold.

### MRR (Mean Reciprocal Rank)

**What it measures:** How high up in the results does the first relevant document appear?

**The question it answers:** "Does the user have to scroll past garbage to find something useful?"

**Formula:**

For a single query:

```
                        1
Reciprocal Rank  =  ─────────────────────────────
                    Rank of first relevant result
```

For multiple queries (the "Mean" in MRR):

```
              1     N
MRR  =  ───────  *  Σ  Reciprocal Rank(query_i)
              N    i=1
```

**Worked example (single query):**

```
Results: [R1, X, R3, R2, X]
          ↑
          First relevant result is at position 1

Reciprocal Rank = 1/1 = 1.00
```

**Another example (worse case):**

```
Results: [X, X, R3, R1, R2]
                ↑
                First relevant result is at position 3

Reciprocal Rank = 1/3 = 0.33
```

**MRR across multiple queries:**

```
Query 1: First relevant at position 1 → RR = 1/1 = 1.00
Query 2: First relevant at position 3 → RR = 1/3 = 0.33
Query 3: First relevant at position 2 → RR = 1/2 = 0.50
Query 4: First relevant at position 1 → RR = 1/1 = 1.00

MRR = (1.00 + 0.33 + 0.50 + 1.00) / 4 = 0.708
```

**Interpretation:** On average, the first relevant result appears near the top of the results. An MRR of 0.708 is good -- it means the first relevant result is typically in position 1 or 2.

**When to optimize for MRR:** When you primarily care about the top result being relevant. Useful for search engines where users focus on the first result. Less important for RAG where the agent processes all retrieved chunks.

### NDCG (Normalized Discounted Cumulative Gain)

NDCG is the most sophisticated metric. It accounts for *graded* relevance (not just relevant/not-relevant) and *position* (relevant results appearing earlier are worth more).

**Conceptually:** A highly relevant document at position 1 is worth more than a somewhat relevant document at position 5. NDCG captures this by discounting the gain of each result by its position.

**Formula (simplified):**

```
                    k      relevance(i)
DCG@k  =  Σ    ─────────────────
                   i=1    log₂(i + 1)

                DCG@k
NDCG@k  =  ──────────────
               IDCG@k

Where IDCG@k is the DCG of the ideal (perfect) ranking.
```

NDCG is useful for evaluation sets where relevance is scored on a scale (0 = irrelevant, 1 = somewhat relevant, 2 = highly relevant). For the AI Doctor project, binary relevance (relevant or not) is sufficient, making Precision@k and Recall@k the primary metrics. NDCG becomes more important if you later add graded relevance to your evaluation set.

### How These Metrics Relate

```
┌─────────────────────────────────────────────────────────────────┐
│                    Retrieval Metrics Map                         │
│                                                                  │
│                    ┌──────────────┐                               │
│                    │   Query      │                               │
│                    └──────┬───────┘                               │
│                           │                                      │
│                    ┌──────▼───────┐                               │
│                    │  Top-k       │                               │
│                    │  Results     │                               │
│                    └──────┬───────┘                               │
│                           │                                      │
│            ┌──────────────┼──────────────┐                       │
│            │              │              │                        │
│     ┌──────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐                │
│     │ Precision@k │ │ Recall@k │ │   MRR       │                │
│     │             │ │          │ │             │                  │
│     │ "How clean  │ │ "How     │ │ "How fast   │                │
│     │  are the    │ │ complete │ │  do we find │                │
│     │  results?"  │ │ are the  │ │  something  │                │
│     │             │ │ results?"│ │  useful?"   │                │
│     │ Focus: what │ │ Focus:   │ │ Focus:      │                │
│     │ we returned │ │ what we  │ │ first hit   │                │
│     │             │ │ missed   │ │ position    │                │
│     └─────────────┘ └──────────┘ └─────────────┘                │
│                                                                  │
│     ┌─────────────────────────────────────────┐                  │
│     │              NDCG@k                     │                  │
│     │  "How good is the ranking overall,      │                  │
│     │   accounting for position and graded     │                  │
│     │   relevance?"                            │                  │
│     │  (Combines precision + ranking quality)  │                  │
│     └─────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

### Building an Evaluation Set

Metrics are only as good as your ground truth. For the AI Doctor project, building an evaluation set means:

1. **Define queries** -- realistic search queries the agent would make (e.g., "metformin renal dosing," "statin side effects monitoring," "ACE inhibitor and potassium interaction")

2. **Label relevant chunks** -- for each query, identify which chunks in your vector store are relevant. This requires clinical knowledge or review.

3. **Store as test fixtures** -- keep query-relevance pairs in a structured format:

```python
# evaluation_set.py
EVAL_SET = [
    {
        "query": "metformin renal dosing guidelines",
        "relevant_chunk_ids": [
            "ada-standards-2025:chunk-12",  # Metformin > Renal Dosing
            "kdigo-ckd:chunk-7",            # Drug Dosing > Metformin
            "fda-metformin:chunk-3",        # Contraindications
            "ada-standards-2025:chunk-18",  # Monitoring > Renal Function
        ],
    },
    {
        "query": "statin therapy monitoring liver enzymes",
        "relevant_chunk_ids": [
            "acc-aha-cholesterol:chunk-15",  # Monitoring > Liver
            "fda-atorvastatin:chunk-5",      # Warnings > Hepatic
        ],
    },
    # ... 50+ query-relevance pairs for a robust eval
]
```

4. **Run evaluations** -- compute Precision@k, Recall@k, and MRR across all queries. Track these over time.

```
AI DOCTOR EXAMPLE:
The project's RAG-ARCH.md targets an evaluation suite of 50+ test
queries with precision@5 > 0.6 and recall@10 > 0.8. This is Phase 8
in the implementation plan.

Why 50+ queries? Fewer queries make your metrics noisy -- one bad
result swings the averages significantly. At 50 queries, the metrics
stabilize and give reliable signal about retrieval quality.

The eval set should cover:
- Common conditions (diabetes, hypertension, CKD)
- Drug-specific queries (metformin dosing, statin interactions)
- Multi-condition queries (metformin + renal impairment)
- Edge cases (drugs not in the knowledge base)
```

---

## 3. Testing RAG Systems

### The 5-Layer Testing Strategy

The AI Doctor project uses a layered testing approach. Each layer tests one component in isolation before testing the composed pipeline. This is directly from the project's RAG-ARCH.md (Section 9) and implemented in the actual test files.

```
┌──────────────────────────────────────────────────────────┐
│  Layer 5: End-to-End Tests                                │
│  "Does the agent use retrieved context correctly?"        │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Layer 4: Integration Tests                       │    │
│  │  "Does the full search pipeline return relevant   │    │
│  │   results?"                                       │    │
│  │                                                   │    │
│  │  ┌──────────────────────────────────────────┐    │    │
│  │  │  Layer 3: Embedding Tests                 │    │    │
│  │  │  "Do similar texts produce similar        │    │    │
│  │  │   vectors?"                               │    │    │
│  │  │                                           │    │    │
│  │  │  ┌──────────────────────────────────┐    │    │    │
│  │  │  │  Layer 2: Chunking Tests          │    │    │    │
│  │  │  │  "Do chunks respect limits?       │    │    │    │
│  │  │  │   Do section paths propagate?"    │    │    │    │
│  │  │  │                                   │    │    │    │
│  │  │  │  ┌──────────────────────────┐    │    │    │    │
│  │  │  │  │  Layer 1: Parsing Tests   │    │    │    │    │
│  │  │  │  │  "Does parse_markdown     │    │    │    │    │
│  │  │  │  │   extract sections?"      │    │    │    │    │
│  │  │  │  └──────────────────────────┘    │    │    │    │
│  │  │  └──────────────────────────────────┘    │    │    │
│  │  └──────────────────────────────────────────┘    │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

Let us walk through each layer with actual test code from the project.

### Layer 1: Parsing Tests

**What you are testing:** Does the markdown parser correctly extract sections, their heading hierarchy, levels, and body text?

**Why this matters:** If parsing is wrong, every downstream step is wrong. A missed heading means a missing section path. A garbled body means garbled embeddings.

**Actual tests from the project** (`backend/tests/test_document_processor.py`):

```python
"""Unit tests for document_processor: markdown parsing and chunking."""

from src.services.document_processor import (
    Section,
    chunk_sections,
    parse_markdown,
)

SAMPLE_MD = """\
# Diabetes Management

Overview of diabetes management guidelines.

## Pharmacologic Therapy

### Metformin

Metformin is the preferred initial agent for type 2 diabetes.
Dose adjustment required when eGFR falls below 45 mL/min.

### Insulin

Insulin therapy should be considered when HbA1c targets are not met.

## Monitoring

Regular HbA1c monitoring every 3 months.
"""


class TestParseMarkdown:
    def test_extracts_correct_sections(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        headings = [s.heading for s in sections]
        assert "Diabetes Management" in headings
        assert "Metformin" in headings
        assert "Insulin" in headings
        assert "Monitoring" in headings

    def test_section_paths(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        by_heading = {s.heading: s for s in sections}

        metformin = by_heading["Metformin"]
        assert metformin.path == [
            "Diabetes Management",
            "Pharmacologic Therapy",
            "Metformin",
        ]

        insulin = by_heading["Insulin"]
        assert insulin.path == [
            "Diabetes Management",
            "Pharmacologic Therapy",
            "Insulin",
        ]

        monitoring = by_heading["Monitoring"]
        assert monitoring.path == ["Diabetes Management", "Monitoring"]

    def test_section_levels(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        by_heading = {s.heading: s for s in sections}

        assert by_heading["Diabetes Management"].level == 1
        assert by_heading["Pharmacologic Therapy"].level == 2
        assert by_heading["Metformin"].level == 3

    def test_body_text_captured(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        by_heading = {s.heading: s for s in sections}
        assert "preferred initial agent" in by_heading["Metformin"].body

    def test_empty_body_sections(self) -> None:
        md = "# Title\n## Empty Section\n## Has Body\nSome text."
        sections = parse_markdown(md)
        bodies = {s.heading: s.body for s in sections}
        assert bodies["Empty Section"] == ""
        assert bodies["Has Body"] == "Some text."
```

**What these tests verify:**

| Test | What it catches |
|------|-----------------|
| `test_extracts_correct_sections` | Parser misses headings or includes non-headings |
| `test_section_paths` | Heading hierarchy is broken (e.g., Metformin not nested under Pharmacologic Therapy) |
| `test_section_levels` | Level numbers wrong (h1=1, h2=2, h3=3) |
| `test_body_text_captured` | Body text not associated with the correct section |
| `test_empty_body_sections` | Empty sections crash the parser or get fake body text |

**Key pattern:** Tests use a realistic but small markdown sample. The sample is defined as a module constant (`SAMPLE_MD`) so every test shares the same fixture. This is important because it means changing the sample updates all tests simultaneously.

### Layer 2: Chunking Tests

**What you are testing:** Does the chunker respect token limits, propagate section paths, and handle edge cases?

**Why this matters:** Chunks are what get embedded and stored. If chunks are too large, they dilute embedding quality. If they break mid-sentence, the embeddings lose semantic coherence. If section paths are missing, metadata filtering breaks.

**Actual tests from the project** (`backend/tests/test_document_processor.py`):

```python
class TestChunkSections:
    def test_basic_chunking(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        chunks = chunk_sections(
            sections,
            document_id="test-doc",
            document_title="Test",
            specialty="endocrinology",
            publication_date=date(2025, 1, 1),
        )
        # Should produce chunks for sections with body text
        assert len(chunks) > 0
        assert all(c.document_id == "test-doc" for c in chunks)
        assert all(c.specialty == "endocrinology" for c in chunks)

    def test_section_path_in_chunk_text(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        chunks = chunk_sections(sections, document_id="test")
        metformin_chunks = [c for c in chunks if "Metformin" in c.section_path]
        assert len(metformin_chunks) > 0
        for chunk in metformin_chunks:
            assert chunk.text.startswith("[")
            assert "Metformin" in chunk.text

    def test_chunk_index_and_total(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        chunks = chunk_sections(sections, document_id="test")
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == total

    def test_max_token_limit_splits(self) -> None:
        """Long sections get split at paragraph boundaries."""
        long_body = "\n\n".join(
            f"Paragraph {i} with enough text to matter." for i in range(50)
        )
        sections = [Section(heading="Long", level=1, body=long_body, path=["Long"])]
        chunks = chunk_sections(sections, max_tokens=100, document_id="test")
        assert len(chunks) > 1
        for chunk in chunks:
            # Rough check: no chunk should be wildly over the limit
            assert len(chunk.text) < 800  # generous upper bound

    def test_empty_sections_skipped(self) -> None:
        sections = [
            Section(heading="Empty", level=1, body="", path=["Empty"]),
            Section(heading="HasBody", level=1, body="Content here.", path=["HasBody"]),
        ]
        chunks = chunk_sections(sections, document_id="test")
        assert len(chunks) == 1
        assert "Content here." in chunks[0].text

    def test_metadata_propagated(self) -> None:
        sections = parse_markdown("# Test\nBody text.")
        chunks = chunk_sections(
            sections,
            document_id="doc-1",
            document_title="My Doc",
            specialty="cardiology",
            document_type="protocol",
            conditions=["CHF"],
            drugs=["metoprolol"],
            publication_date=date(2025, 6, 1),
        )
        assert len(chunks) == 1
        c = chunks[0]
        assert c.document_title == "My Doc"
        assert c.conditions == ["CHF"]
        assert c.drugs == ["metoprolol"]
        assert c.publication_date == date(2025, 6, 1)
```

**Critical test: `test_section_path_in_chunk_text`.** This verifies that every chunk starts with its section path prefix (e.g., `[Diabetes Management > Pharmacologic Therapy > Metformin]`). This prefix is what gives the embedding model context about where the chunk lives in the document hierarchy. Without it, "Administer 5mg" is meaningless because the embedding does not know which drug or condition.

**Critical test: `test_max_token_limit_splits`.** This verifies that long sections get split into multiple chunks without exceeding the token limit. The assertion uses a generous upper bound (800 characters) rather than an exact limit because token counting is approximate (the chunker estimates ~4 characters per token).

### Layer 3: Embedding and Storage Tests

**What you are testing:** Does the embedding function return vectors of the correct dimension? Does the storage layer persist chunks with correct payloads? Is ingestion idempotent?

**Why this matters:** If embeddings have the wrong dimension, Qdrant rejects them. If payload fields are missing, metadata filtering breaks. If ingestion is not idempotent, re-running the ingest script creates duplicates.

**Actual tests from the project** (`backend/tests/test_rag_service.py`):

```python
"""Unit tests for rag_service: embedding, storage, search, XML formatting."""

from unittest.mock import MagicMock
import pytest
from qdrant_client import QdrantClient

from src.models.rag import DocumentChunk, RetrievalResult
from src.services import rag_service


def _fake_embedding(dim: int = 768) -> list[float]:
    """Deterministic fake embedding vector."""
    return [0.1] * dim


@pytest.fixture
def in_memory_qdrant(monkeypatch: pytest.MonkeyPatch) -> QdrantClient:
    """Use in-memory Qdrant for tests."""
    client = QdrantClient(":memory:")
    monkeypatch.setattr(rag_service, "_qdrant_client", client)
    monkeypatch.setattr(rag_service, "get_qdrant_client", lambda: client)
    return client


@pytest.fixture
def mock_genai(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock the GenAI client so no real API calls are made."""
    mock_client = MagicMock()
    monkeypatch.setattr(rag_service, "_genai_client", mock_client)
    monkeypatch.setattr(rag_service, "get_genai_client", lambda: mock_client)
    monkeypatch.setattr("src.config.settings.google_api_key", "")
    return mock_client


class TestEmbedText:
    def test_returns_vector(self, mock_genai: MagicMock) -> None:
        mock_genai.models.embed_content.return_value = _mock_embed_response(1)
        result = rag_service.embed_text("test query")
        assert len(result) == 768
        assert all(isinstance(v, float) for v in result)

    def test_calls_with_query_task_type(self, mock_genai: MagicMock) -> None:
        mock_genai.models.embed_content.return_value = _mock_embed_response(1)
        rag_service.embed_text("test query")
        call_kwargs = mock_genai.models.embed_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.task_type == "RETRIEVAL_QUERY"


class TestUpsertChunks:
    def test_upsert_and_count(self, in_memory_qdrant: QdrantClient) -> None:
        rag_service.ensure_collection()
        chunks = [_make_chunk(chunk_index=i, total_chunks=3) for i in range(3)]
        vectors = [_fake_embedding() for _ in chunks]
        rag_service.upsert_chunks(chunks, vectors)

        info = in_memory_qdrant.get_collection("clinical_guidelines")
        assert info.points_count == 3

    def test_upsert_idempotent(self, in_memory_qdrant: QdrantClient) -> None:
        """Same document_id + chunk_index -> same UUID5 -> no duplicates."""
        rag_service.ensure_collection()
        chunk = _make_chunk()
        vector = _fake_embedding()
        rag_service.upsert_chunks([chunk], [vector])
        rag_service.upsert_chunks([chunk], [vector])  # same data

        info = in_memory_qdrant.get_collection("clinical_guidelines")
        assert info.points_count == 1

    def test_payload_fields_stored(self, in_memory_qdrant: QdrantClient) -> None:
        rag_service.ensure_collection()
        chunk = _make_chunk(text="Metformin renal dosing info")
        rag_service.upsert_chunks([chunk], [_fake_embedding()])

        points, _ = in_memory_qdrant.scroll(
            collection_name="clinical_guidelines", limit=1, with_payload=True
        )
        payload = points[0].payload
        assert payload["text"] == "Metformin renal dosing info"
        assert payload["document_id"] == "doc-1"
        assert payload["specialty"] == "endocrinology"
        assert payload["conditions"] == ["diabetes"]
```

### The In-Memory Qdrant Pattern

This pattern deserves special attention because it is one of the most important testing decisions in the project.

```python
@pytest.fixture
def in_memory_qdrant(monkeypatch: pytest.MonkeyPatch) -> QdrantClient:
    """Use in-memory Qdrant for tests."""
    client = QdrantClient(":memory:")
    monkeypatch.setattr(rag_service, "_qdrant_client", client)
    monkeypatch.setattr(rag_service, "get_qdrant_client", lambda: client)
    return client
```

**What this does:** Creates a Qdrant client that stores everything in memory (no disk, no Docker container, no network). The `monkeypatch` replaces the production Qdrant client in `rag_service` with this in-memory version.

**Why this matters:**

| Aspect | Docker Qdrant | In-Memory Qdrant |
|--------|---------------|------------------|
| Setup time | 2-5 seconds (container start) | < 1 millisecond |
| Test execution | 200-500ms per test | < 50ms per test |
| CI dependency | Requires Docker in CI | No Docker needed |
| Isolation | Must clean up between tests | Each fixture creates fresh instance |
| Total test suite | 5-15 seconds | < 1 second |
| API compatibility | Full REST + gRPC | Same Python client API |

```
AI DOCTOR EXAMPLE:
The AI Doctor backend has ~20 RAG-related tests across
test_document_processor.py and test_rag_service.py.

With Docker Qdrant: ~10 seconds total (container startup + tests)
With in-memory Qdrant: < 1 second total

This is not a micro-optimization. Fast tests get run frequently.
Slow tests get skipped. When you are iterating on chunking strategy
or search parameters, running tests in under a second versus waiting
10 seconds is the difference between testing every change and
testing once before commit.
```

**Key detail:** `QdrantClient(":memory:")` supports the same API as the real client. Collections, upserts, search, filtering -- all work identically. The only limitation is that data is lost when the test ends, which is exactly what you want for test isolation.

### Layer 4: Integration Tests (Search Pipeline)

**What you are testing:** Does the full search pipeline -- embed query, search Qdrant, filter by metadata, format results -- return relevant results?

**Actual tests from the project** (`backend/tests/test_rag_service.py`):

```python
class TestSearch:
    def test_returns_results(
        self, in_memory_qdrant: QdrantClient, mock_genai: MagicMock
    ) -> None:
        # Setup: create collection, upsert a chunk
        rag_service.ensure_collection()
        chunk = _make_chunk(text="Metformin dose adjustment for renal impairment")
        rag_service.upsert_chunks([chunk], [_fake_embedding()])

        # Mock the query embedding to return the same vector (perfect match)
        mock_genai.models.embed_content.return_value = _mock_embed_response(1)

        results = rag_service.search("metformin renal dosing")
        assert len(results) == 1
        assert isinstance(results[0], RetrievalResult)
        assert results[0].source_id == 1
        assert results[0].score > 0

    def test_specialty_filter(
        self, in_memory_qdrant: QdrantClient, mock_genai: MagicMock
    ) -> None:
        rag_service.ensure_collection()
        endo_chunk = _make_chunk(
            text="Diabetes chunk", specialty="endocrinology", document_id="d1"
        )
        cardio_chunk = _make_chunk(
            text="Heart chunk", specialty="cardiology", document_id="d2"
        )
        rag_service.upsert_chunks(
            [endo_chunk, cardio_chunk],
            [_fake_embedding(), _fake_embedding()],
        )

        mock_genai.models.embed_content.return_value = _mock_embed_response(1)
        results = rag_service.search("diabetes", specialty="endocrinology")
        specialties = {r.chunk.specialty for r in results}
        assert "cardiology" not in specialties
```

**Why the embedding is mocked:** These tests verify the search pipeline logic, not embedding quality. By using `_fake_embedding()` (a constant `[0.1] * 768` vector) for both document and query embeddings, we guarantee a perfect cosine similarity match. This isolates the search logic from embedding quality -- a different concern tested at Layer 3.

**The specialty filter test** is critical for medical RAG. When the agent searches for "diabetes management" and specifies `specialty="endocrinology"`, cardiology guidelines must not appear. The test verifies this by upserting chunks from two specialties and asserting the filter works.

### Layer 5: End-to-End Tests

**What you are testing:** Does the agent call the search tool, receive results, and generate a briefing that cites the retrieved sources?

**Why this is the hardest layer:** It involves the full agent loop -- Claude Agent SDK, MCP server, tool execution, structured output. The LLM must be mocked to make tests deterministic.

**Test pattern (conceptual):**

```python
# Conceptual end-to-end test for the RAG agent
async def test_agent_cites_retrieved_sources(
    mock_agent_query,    # Mocked query() that simulates agent behavior
    in_memory_qdrant,    # In-memory Qdrant with pre-loaded guidelines
    mock_genai,          # Mocked embedding API
):
    # Setup: ingest a diabetes guideline
    ingest_test_guideline("ada-standards-sample.md")

    # Execute: generate briefing for a diabetic patient
    briefing = await generate_briefing(diabetic_patient_record)

    # Assert: briefing references the ingested guideline
    assert any(
        flag.source == "ai" for flag in briefing.flags
    )
    assert len(briefing.citations) > 0
    assert any(
        "ADA Standards" in cite.document_title
        for cite in briefing.citations
    )
```

**Why Layer 5 is tested last:** It depends on all previous layers working. If Layer 1 (parsing) is broken, the guideline does not get chunked correctly. If Layer 2 (chunking) is broken, the embeddings are wrong. If Layer 3 (embedding) is broken, search returns garbage. If Layer 4 (search) is broken, the agent gets no context. Only when all four layers pass can you meaningfully test the end-to-end flow.

### XML Formatting Tests

One more layer of testing that sits between search and agent: verifying the XML format that the agent receives.

```python
class TestFormatAsXmlSources:
    def test_formats_results(self) -> None:
        chunk = _make_chunk(text="Metformin reduces HbA1c.")
        results = [RetrievalResult(chunk=chunk, score=0.89, source_id=1)]
        xml = rag_service.format_as_xml_sources(results)
        assert "<clinical_guidelines>" in xml
        assert 'id="1"' in xml
        assert 'document="Test Document"' in xml
        assert "Metformin reduces HbA1c." in xml
        assert "</clinical_guidelines>" in xml

    def test_empty_results(self) -> None:
        xml = rag_service.format_as_xml_sources([])
        assert "No relevant guidelines found" in xml

    def test_multiple_sources(self) -> None:
        chunks = [
            _make_chunk(text=f"Chunk {i}", chunk_index=i, total_chunks=3)
            for i in range(3)
        ]
        results = [
            RetrievalResult(chunk=c, score=0.9 - i * 0.1, source_id=i + 1)
            for i, c in enumerate(chunks)
        ]
        xml = rag_service.format_as_xml_sources(results)
        assert xml.count("<source ") == 3
        assert 'id="1"' in xml
        assert 'id="3"' in xml
```

**Why test XML formatting separately?** The XML format is the contract between the search tool and the agent. If the XML structure changes (attribute names, nesting, escaping), the agent's ability to parse and cite sources breaks. These tests ensure the contract is stable.

**The empty results test** (`test_empty_results`) is particularly important. When the search returns nothing, the agent must receive an explicit "No relevant guidelines found" message so it can state this in its output rather than hallucinating guidelines.

### Testing Summary

```
┌───────────┬────────────────────────┬───────────────────────┬───────────┐
│   Layer   │     What is Tested     │      Mocked/Fake      │  Speed    │
├───────────┼────────────────────────┼───────────────────────┼───────────┤
│ 1: Parse  │ Heading extraction,    │ Nothing               │ < 1ms     │
│           │ hierarchy, body text   │ (pure functions)      │           │
├───────────┼────────────────────────┼───────────────────────┼───────────┤
│ 2: Chunk  │ Token limits, section  │ Nothing               │ < 1ms     │
│           │ paths, metadata        │ (pure functions)      │           │
├───────────┼────────────────────────┼───────────────────────┼───────────┤
│ 3: Embed  │ Vector dimensions,     │ GenAI API (mocked)    │ < 5ms     │
│ + Store   │ payload storage,       │ Qdrant (in-memory)    │           │
│           │ idempotent upserts     │                       │           │
├───────────┼────────────────────────┼───────────────────────┼───────────┤
│ 4: Search │ Search pipeline,       │ GenAI API (mocked)    │ < 10ms   │
│           │ metadata filtering,    │ Qdrant (in-memory)    │           │
│           │ XML formatting         │                       │           │
├───────────┼────────────────────────┼───────────────────────┼───────────┤
│ 5: E2E    │ Agent uses context,    │ GenAI API (mocked)    │ < 100ms  │
│           │ cites sources,         │ Qdrant (in-memory)    │           │
│           │ handles no results     │ Agent SDK (mocked)    │           │
└───────────┴────────────────────────┴───────────────────────┴───────────┘

Total test suite time (all layers): < 1 second
```

---

## 4. Common Failure Modes and Anti-Patterns

This section covers the most common ways RAG systems fail, drawing from the project's RAG-ARCH.md Section 10 and practical experience. For each failure mode, we describe the symptom, explain why it happens, and provide the mitigation used in the AI Doctor project.

### Failure Mode 1: Naive Chunking

**Symptom:** The agent generates answers with phrases like "as mentioned above" or references to context that is not present. Chunks contain fragments like "Administer 5mg" with no indication of which drug, condition, or patient population.

**Why it happens:** Fixed-size chunking (e.g., "split every 500 tokens") ignores document structure. A chunk boundary can land in the middle of a dosing table, between a drug name and its contraindications, or between a section header and its content.

```
FIXED-SIZE CHUNKING (WRONG):

    ┌────────────────────────────────┐
    │ Chunk 1 (500 tokens)           │
    │                                │
    │ ## Metformin                   │
    │ Metformin is the preferred     │
    │ initial agent for type 2       │
    │ diabetes. Dose adjustment      │
    │ required when eGFR falls below │
    ├─── CHUNK BOUNDARY ─────────────┤  ← Splits mid-sentence!
    │ Chunk 2 (500 tokens)           │
    │                                │
    │ 45 mL/min. Contraindicated     │
    │ when eGFR < 30.                │
    │                                │
    │ ## Insulin                     │
    │ Insulin therapy should be      │
    │ considered when HbA1c targets  │
    └────────────────────────────────┘
```

**Mitigation: Structure-aware chunking.** The AI Doctor project chunks at section boundaries. Each chunk corresponds to a document section, with the section path prepended:

```
STRUCTURE-AWARE CHUNKING (CORRECT):

    ┌────────────────────────────────────────────┐
    │ Chunk 1                                     │
    │ [Diabetes Management > Pharmacologic        │
    │  Therapy > Metformin]                       │
    │                                             │
    │ Metformin is the preferred initial agent     │
    │ for type 2 diabetes. Dose adjustment        │
    │ required when eGFR falls below 45 mL/min.   │
    │ Contraindicated when eGFR < 30.             │
    └────────────────────────────────────────────┘

    ┌────────────────────────────────────────────┐
    │ Chunk 2                                     │
    │ [Diabetes Management > Pharmacologic        │
    │  Therapy > Insulin]                         │
    │                                             │
    │ Insulin therapy should be considered when    │
    │ HbA1c targets are not met.                  │
    └────────────────────────────────────────────┘
```

The section path prefix (`[Diabetes Management > Pharmacologic Therapy > Metformin]`) gives the embedding model critical context. The embedding for "Metformin is the preferred initial agent" with this prefix is much more useful than the same text without it.

### Failure Mode 2: Mixed Embedding Models

**Symptom:** Search returns completely irrelevant results despite having the correct documents in the vector store. Cosine similarity scores are unexpectedly low across the board.

**Why it happens:** Different embedding models produce vectors in different semantic spaces. If you index documents with Model A and query with Model B, the vectors are incomparable. It is like indexing a library using the Dewey Decimal system and then searching with Library of Congress classification codes -- they organize knowledge differently.

```
MODEL A EMBEDDING SPACE:          MODEL B EMBEDDING SPACE:
(used for indexing)               (used for querying)

         "diabetes"                        "diabetes"
             ●                                 ●
            / \                               / \
           /   \                             /   \
  "metformin"  "insulin"          "heart disease"  "insulin"
       ●           ●                   ●               ●

The same word occupies a DIFFERENT position in each space.
Cosine similarity across spaces is meaningless.
```

**Mitigation:** Document your active embedding model. The AI Doctor project uses Vertex AI `text-embedding-005` (768 dimensions). If you switch models, you must re-embed the entire corpus. There is no shortcut -- partial re-embedding creates a mixed-model collection that produces garbage results.

The project's RAG-ARCH.md states this explicitly: "Never mix embedding models. Switching models = full re-embed of entire corpus."

### Failure Mode 3: Lost-in-the-Middle Problem

**Symptom:** The agent correctly retrieves all relevant chunks but ignores information from chunks in the middle of the context. The briefing references the first and last retrieved sources but never the middle ones.

**Why it happens:** Research has shown that LLMs pay disproportionate attention to the beginning and end of their context window. Information placed in the middle of a long context is more likely to be overlooked. This is sometimes called the "lost in the middle" phenomenon.

```
ATTENTION DISTRIBUTION OVER RETRIEVED CHUNKS:

Attention
    │
    │  ████                                        ████
    │  ████                                        ████
    │  ████                                        ████
    │  ████  ████                          ████    ████
    │  ████  ████  ████            ████    ████    ████
    │  ████  ████  ████  ████  ████  ████  ████    ████
    │  ████  ████  ████  ████  ████  ████  ████    ████
    └──────────────────────────────────────────────────
       1     2     3     4     5     6     7       8
                    Retrieved Chunks

       HIGH          LOW ATTENTION          HIGH
     ATTENTION        (DANGER ZONE)       ATTENTION
```

**Mitigation:**

1. **Limit the number of retrieved chunks.** The AI Doctor uses a default of 5 chunks per search call. This is enough to provide relevant context without creating a long middle section.

2. **Order by relevance.** The most relevant chunks (highest cosine similarity) appear first. Since LLMs attend to the beginning more, the most important information gets the most attention.

3. **Multiple focused searches.** Instead of one broad search returning 20 chunks, the agent makes multiple targeted searches (e.g., "metformin renal dosing" then "metformin drug interactions"), each returning 5 focused chunks. The `max_turns=4` in the agent configuration allows for this multi-search pattern.

### Failure Mode 4: Over-Retrieval

**Symptom:** The agent produces answers that are vaguely correct but not specific. It generates generic summaries instead of precise clinical guidance. Citations reference documents that are tangentially related but not directly relevant.

**Why it happens:** Returning too many chunks (high k with no score threshold) floods the context with marginally relevant information. The agent cannot distinguish signal from noise when 15 of 20 retrieved chunks are only loosely related.

```
OVER-RETRIEVAL EXAMPLE:

Query: "metformin renal dosing"
k = 20, no score threshold

Results:
  Score  Document
  ─────  ─────────────────────────────────────
  0.92   ADA Metformin Renal Dosing          ← Highly relevant
  0.87   KDIGO Drug Dosing: Metformin        ← Highly relevant
  0.83   FDA Label: Metformin Warnings       ← Relevant
  0.71   ADA General Diabetes Overview       ← Somewhat relevant
  0.65   Diabetes Prevention Guidelines      ← Marginally relevant
  0.58   KDIGO General CKD Staging           ← Marginally relevant
  0.52   Insulin Therapy Guidelines          ← Barely relevant
  0.45   Hypertension in Diabetes            ← Not relevant
  0.41   Statin Therapy Recommendations      ← Not relevant
  0.38   General Drug Interaction Database   ← Not relevant
  ...
  0.22   Pediatric Vaccination Schedule      ← Completely irrelevant
```

**Mitigation:**

1. **Score threshold.** The AI Doctor uses a threshold of 0.5. Any result with cosine similarity below 0.5 is dropped, regardless of k. This eliminates the low-quality tail.

2. **Smaller k.** The default is `limit=5`, not 20. Five high-quality chunks are more useful than twenty mixed-quality ones.

3. **The combination matters.** With k=5 and threshold=0.5, the agent gets *at most* 5 results, and each result exceeds the quality floor. In the example above, only the top 3 results (scores 0.92, 0.87, 0.83) would be returned.

### Failure Mode 5: Under-Retrieval

**Symptom:** The agent states "no relevant guidelines found" for queries that should have matches, or produces briefings missing important clinical context. Recall is low.

**Why it happens:** k is set too low, the score threshold is too high, or the chunking/embedding quality is poor. A threshold of 0.8 might seem like it ensures quality, but it can filter out legitimate results that score 0.7 due to vocabulary differences.

**Mitigation:**

1. **Tune the threshold empirically.** The project's 0.5 threshold was chosen to balance recall and precision. Test with your actual data -- not theoretical values.

2. **Use the evaluation set.** Compute Recall@k across your test queries. If recall drops below 0.8 (the project target), investigate whether the threshold is too aggressive.

3. **Multiple search strategies.** The agent can refine its query and search again. If "metformin renal dosing guidelines" returns nothing, the agent might try "metformin kidney" in a follow-up turn.

### Failure Mode 6: Threshold Too Low

**Symptom:** The agent confidently cites guidelines that are not actually relevant to the clinical question. The briefing includes accurate-sounding citations that, on review, come from unrelated documents.

**Why it happens:** With a very low threshold (e.g., 0.2), the search returns anything vaguely in the same domain. A search for "metformin renal dosing" returns a chunk about "renal artery stenosis treatment" because both contain the word "renal" and score 0.3 in embedding space.

**Mitigation:** This is the flip side of under-retrieval. The 0.5 threshold is a balanced starting point. Monitor precision over time and adjust.

### Failure Mode 7: No Metadata Filtering

**Symptom:** The agent returns cardiology guidelines for a nephrology query, or outdated 2018 guidelines when 2025 versions exist. The results are semantically similar (correct topic) but contextually wrong (wrong specialty or version).

**Why it happens:** Vector similarity alone does not capture metadata constraints. "Metformin dosing" in a cardiology context (for diabetic patients with heart failure) has a very similar embedding to "Metformin dosing" in an endocrinology context (for general type 2 diabetes management). Without metadata filtering, both appear in results.

```
WITHOUT METADATA FILTERING:

Query: "metformin dosing" (patient has diabetes, no cardiac history)

  Score  Specialty       Document
  ─────  ──────────────  ─────────────────────────────────
  0.91   cardiology      Metformin in Heart Failure
  0.89   endocrinology   ADA: Standard Metformin Dosing     ← This is the one you want
  0.85   nephrology      KDIGO: Metformin Renal Adjustment
  0.82   cardiology      CV Risk and Diabetes Medications

The cardiology chunk scores highest because the embedding
is almost identical, but it discusses metformin in the context
of heart failure -- not relevant for this patient.
```

**Mitigation:** The AI Doctor's search tool accepts an optional `specialty` parameter. When provided, it adds a Qdrant filter that restricts results to chunks with matching specialty metadata. The rich payload stored with each chunk (specialty, conditions, drugs, publication date) enables precise filtering.

### Anti-Pattern Summary

| # | Failure Mode | Symptom | Mitigation |
|---|-------------|---------|------------|
| 1 | Naive chunking | "As mentioned above" / lost context | Structure-aware chunking with section paths |
| 2 | Mixed embedding models | Low similarity scores everywhere | Single model; full re-embed on switch |
| 3 | Lost-in-the-middle | Middle chunks ignored | Limit to 5 chunks; order by relevance |
| 4 | Over-retrieval | Generic, unfocused answers | k=5, score threshold=0.5 |
| 5 | Under-retrieval | Missing important context | Tune threshold empirically; multiple searches |
| 6 | Threshold too low | Citing irrelevant documents | Score threshold >= 0.5 |
| 7 | No metadata filtering | Wrong specialty/version returned | Rich payload metadata; filter in tool |

---

## 5. Production Considerations

### Re-Indexing Strategies

Clinical guidelines get updated. The ADA Standards of Care in Diabetes are revised annually. When an update is published, you need to re-ingest the new version. This raises several questions:

**How to prevent duplicate documents after re-ingestion?**

The AI Doctor project uses UUID5 deterministic IDs. The point ID for each chunk is computed as:

```python
import uuid

point_id = uuid.uuid5(
    uuid.NAMESPACE_DNS,
    f"{document_id}:{chunk_index}"
)
```

UUID5 is deterministic: the same `document_id` and `chunk_index` always produce the same UUID. When you re-run the ingest script with updated content for the same document, Qdrant performs an *upsert* -- updating the existing point rather than creating a duplicate.

```
FIRST INGESTION:
  "ada-standards-2025:0" → UUID5 → abc123 → [vector_v1, payload_v1]
  "ada-standards-2025:1" → UUID5 → def456 → [vector_v1, payload_v1]
  "ada-standards-2025:2" → UUID5 → ghi789 → [vector_v1, payload_v1]

RE-INGESTION (updated content):
  "ada-standards-2025:0" → UUID5 → abc123 → [vector_v2, payload_v2]  (UPDATED)
  "ada-standards-2025:1" → UUID5 → def456 → [vector_v2, payload_v2]  (UPDATED)
  "ada-standards-2025:2" → UUID5 → ghi789 → [vector_v2, payload_v2]  (UPDATED)

Points count: still 3, not 6. Idempotent.
```

This is verified by the `test_upsert_idempotent` test in the project:

```python
def test_upsert_idempotent(self, in_memory_qdrant: QdrantClient) -> None:
    """Same document_id + chunk_index -> same UUID5 -> no duplicates."""
    rag_service.ensure_collection()
    chunk = _make_chunk()
    vector = _fake_embedding()
    rag_service.upsert_chunks([chunk], [vector])
    rag_service.upsert_chunks([chunk], [vector])  # same data

    info = in_memory_qdrant.get_collection("clinical_guidelines")
    assert info.points_count == 1
```

**What if the updated document has more or fewer chunks?**

This is a subtle problem. If the 2025 ADA Standards had 28 chunks and the 2026 version has 25, the old chunks 25-27 would remain as orphans in the vector store. The mitigation is to delete all points for a document ID before re-ingesting:

```python
# Before re-ingestion, remove old chunks for this document
qdrant_client.delete(
    collection_name="clinical_guidelines",
    points_selector=models.FilterSelector(
        filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value="ada-standards-2025"),
                ),
            ],
        ),
    ),
)
```

Then upsert the new chunks. The UUID5 IDs ensure any chunks that happen to share the same document_id + chunk_index mapping will be cleanly overwritten.

```
AI DOCTOR EXAMPLE:
The CLI ingest script (scripts/ingest_docs.py) handles re-indexing.
You can safely re-run it whenever guidelines are updated:

  uv run python scripts/ingest_docs.py --source docs/guidelines/

UUID5 deterministic IDs mean this is idempotent -- running it twice
produces the same result as running it once. No manual cleanup needed
for documents that have the same number of chunks. For documents with
changed chunk counts, the delete-before-upsert pattern ensures clean
re-indexing.
```

### Threshold Tuning

The score threshold (0.5 in the AI Doctor project) determines the quality floor for retrieved results. Tuning this value requires empirical experimentation with your actual data.

**How to tune the threshold:**

1. **Collect query-result pairs.** Run your evaluation set queries and record the scores of all returned results, along with their relevance labels.

2. **Plot score distribution:**

```
Number of
results
    │
 20 │     ████
    │     ████
 15 │     ████  ████
    │     ████  ████
 10 │     ████  ████  ████
    │  █  ████  ████  ████
  5 │  ████████  ████  ████  ████
    │  ████████  ████  ████  ████  ████        ██
    └──────────────────────────────────────────────
      0.2  0.3  0.4  0.5  0.6  0.7  0.8  0.9  1.0
                        Score

      ◄─── Irrelevant ───►◄─── Relevant ───►
                          ↑
                    Threshold = 0.5
```

3. **Find the separation point.** The ideal threshold sits between the irrelevant and relevant score distributions. If they overlap heavily, your embeddings need improvement (better chunking, better model).

4. **Evaluate metrics at different thresholds:**

| Threshold | Precision@5 | Recall@10 | Notes |
|-----------|-------------|-----------|-------|
| 0.3 | 0.42 | 0.95 | Too much noise |
| 0.4 | 0.55 | 0.90 | Better, still noisy |
| **0.5** | **0.65** | **0.82** | **Good balance** |
| 0.6 | 0.78 | 0.68 | Precision high, recall dropping |
| 0.7 | 0.88 | 0.45 | Missing too many results |

The 0.5 threshold for the AI Doctor project hits both targets: precision@5 > 0.6 and recall@10 > 0.8.

### Latency Budgets

Every agent tool call adds latency to the briefing generation. The RAG tool involves two API calls (embed query + search) plus network time.

```
LATENCY BREAKDOWN FOR A SINGLE RAG TOOL CALL:

┌────────────────────────────────────────────────────────────┐
│                                                            │
│  Embed query (Vertex AI API)            100-200ms          │
│  ├── Network round trip                  50-100ms          │
│  └── Model computation                   50-100ms          │
│                                                            │
│  Vector search (Qdrant)                  10-50ms           │
│  ├── HNSW approximate search              5-20ms           │
│  ├── Metadata filtering                   2-10ms           │
│  └── Payload retrieval                    3-20ms           │
│                                                            │
│  Result formatting                         < 1ms           │
│                                                            │
│  TOTAL per tool call:                  110-250ms           │
│                                                            │
│  With 2 tool calls per briefing:       220-500ms           │
│                                                            │
│  Non-functional requirement target:     < 500ms P95        │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**End-to-end briefing latency** includes the LLM reasoning time (which dominates):

```
FULL BRIEFING LATENCY:

  Agent turn 1: Read patient record + decide what to search   ~2s (LLM)
  Tool call 1:  Embed + search                                ~200ms
  Agent turn 2: Read results, decide if more search needed     ~2s (LLM)
  Tool call 2:  Embed + search (optional)                      ~200ms
  Agent turn 3: Generate structured briefing with citations    ~4s (LLM)
  ──────────────────────────────────────────────────────────────
  TOTAL:                                                       ~8-10s

  Non-functional requirement: < 15s (NF2 from RAG-ARCH.md)
```

The tool call latency (< 500ms) is a small fraction of the total. The LLM reasoning time dominates. This is why the non-functional requirement for tool call latency (NF1: < 500ms P95) is separate from the end-to-end requirement (NF2: < 15s).

**Optimization opportunities:**

| Technique | Savings | Complexity |
|-----------|---------|------------|
| Cache embeddings for common queries | 100-200ms per cached query | Low |
| Qdrant gRPC instead of REST | 10-30ms per search | Low |
| Colocate Qdrant with backend | 20-50ms network savings | Medium |
| Reduce embedding dimensions | Faster search, less storage | Medium (requires re-embed) |

### Document Freshness

Clinical guidelines are updated on regular schedules. Managing document freshness in a RAG system means tracking versions and ensuring the agent always retrieves the most current guidance.

**Strategies for document freshness:**

1. **Publication date in metadata.** Each chunk carries a `publication_date` field. The search tool can filter by date or prefer recent documents.

2. **Document versioning.** Use the document ID to encode version: `ada-standards-2025` vs `ada-standards-2026`. When a new version is ingested, delete the old version's chunks.

3. **Ingestion timestamps.** Track when each document was last ingested. Alert when ingestion is older than a threshold (e.g., "ADA Standards were ingested 14 months ago -- a new version may be available").

4. **No mixed versions.** Never have chunks from the 2025 and 2026 versions of the same guideline in the store simultaneously. The agent has no way to know which version is authoritative if both are present.

```
AI DOCTOR EXAMPLE:
The publication_date field in the chunk payload enables freshness-
aware retrieval. If two chunks about metformin dosing have similar
semantic scores but different publication dates:

  Score: 0.87  |  ADA Standards 2025  |  pub: 2025-01-01
  Score: 0.85  |  ADA Standards 2024  |  pub: 2024-01-01

The agent (or the search tool) should prefer the 2025 version.
In V1, freshness is handled by only ingesting the latest version
of each guideline. In V2, a date-based filter or boost could
automate this preference.
```

### Monitoring

In production, retrieval quality can degrade silently. New documents change the vector space. Model updates change embedding distributions. Without monitoring, you discover regression only when a clinician notices a bad briefing.

**What to monitor:**

| Metric | What it catches | How to measure |
|--------|-----------------|----------------|
| Average top-1 score | Embedding quality drift | Log search scores; alert on sustained drops |
| Results per query | Under/over-retrieval trends | Log result counts; alert on sudden changes |
| Score threshold hit rate | Threshold too aggressive | % of queries with 0 results after threshold |
| Tool call latency | Infra degradation | Log embed + search time; alert on P95 > 500ms |
| Collection point count | Orphaned or missing docs | Compare expected vs actual point count |
| Eval set regression | Overall quality drift | Run eval suite weekly; compare to baseline |

**The simplest monitoring:** Log every tool call with the query, number of results, and top score. A weekly script computes averages and flags anomalies.

### Cost

Embedding API calls and vector storage are not free. Understanding the cost model helps you budget and optimize.

**Embedding costs (Vertex AI):**

```
text-embedding-005 pricing (approximate):
  $0.0001 per 1,000 characters embedded

Ingestion cost for 100 clinical guideline documents:
  Average document: 5,000 words ≈ 25,000 characters
  100 docs × 25,000 chars = 2,500,000 characters
  Cost: 2,500 × $0.0001 = $0.25

Query embedding cost:
  Average query: 50 characters
  1,000 queries/day × 50 chars = 50,000 characters
  Daily cost: 50 × $0.0001 = $0.005
```

Embedding costs are negligible for the AI Doctor project's scale. The LLM (Claude) costs dominate.

**Qdrant hosting costs:**

| Option | Cost | Best for |
|--------|------|----------|
| Self-hosted Docker | Free (plus server costs) | Development, small deployments |
| Qdrant Cloud (free tier) | $0 (1GB storage, 1M vectors) | Prototypes, small projects |
| Qdrant Cloud (production) | ~$25-100/month | Production with SLA |

For V1 of the AI Doctor project, the self-hosted Docker option (alongside PostgreSQL in docker-compose) is sufficient.

---

## 6. Hybrid Search and Advanced Techniques

This section previews V2+ features. The concepts are covered at a high level to build your mental model. No implementation details -- these will be addressed when the features are built.

### BM25 (Keyword Search)

**What it is:** BM25 is a traditional keyword-based search algorithm. It ranks documents by term frequency and inverse document frequency -- essentially, "how many times does the search term appear in the document, weighted by how rare that term is across all documents?"

**Why it matters for medical RAG:** Semantic search (what we use in V1) understands meaning. "Renal impairment" and "kidney dysfunction" are semantically similar, so vector search finds both. But semantic search can *miss* exact medical terms. "eGFR" and "estimated glomerular filtration rate" have similar embeddings, but a search for the drug name "empagliflozin" might return results about other SGLT2 inhibitors because the embeddings are close in concept space.

BM25 does not understand meaning, but it finds exact term matches reliably. If "empagliflozin" appears in a document, BM25 will find it.

```
SEMANTIC SEARCH STRENGTH:        BM25 STRENGTH:
"kidney problems"                "empagliflozin"
  → finds "renal impairment"      → finds documents with exactly
  → finds "nephropathy"              "empagliflozin" in the text
  → finds "CKD staging"           → misses "SGLT2 inhibitors" (no
  → misses exact drug names          keyword match)

Neither alone is sufficient for medical search.
```

### Hybrid Search

**What it is:** Combine BM25 keyword scores with vector similarity scores to produce a final ranking. The most common combination method is **Reciprocal Rank Fusion (RRF)**:

```
RECIPROCAL RANK FUSION:

BM25 Results (by keyword):     Vector Results (by embedding):
  Rank 1: Doc A                  Rank 1: Doc C
  Rank 2: Doc C                  Rank 2: Doc A
  Rank 3: Doc D                  Rank 3: Doc B
  Rank 4: Doc B                  Rank 4: Doc D

RRF Score = Σ  1 / (k + rank_in_list)   (k=60 is typical)

Doc A: 1/(60+1) + 1/(60+2) = 0.0164 + 0.0161 = 0.0325
Doc C: 1/(60+2) + 1/(60+1) = 0.0161 + 0.0164 = 0.0325
Doc B: 1/(60+4) + 1/(60+3) = 0.0156 + 0.0159 = 0.0315
Doc D: 1/(60+3) + 1/(60+4) = 0.0159 + 0.0156 = 0.0315

Final ranking: Doc A/C (tied) > Doc B/D (tied)

Docs that rank well in BOTH systems score highest.
```

**V2+ feature.** Qdrant natively supports hybrid search with RRF. The search tool would be updated to issue both a vector search and a BM25 search, then fuse the results.

### Reranking

**What it is:** After retrieving top-k candidates (from vector search, BM25, or hybrid), pass them through a **cross-encoder** model that scores each (query, document) pair for relevance. Cross-encoders are more accurate than bi-encoders (what embedding models are) but much slower -- they cannot be pre-computed, so they are used only on the small candidate set.

```
RETRIEVAL + RERANKING PIPELINE:

  Query: "metformin renal dosing"
         │
         ▼
  ┌──────────────────┐
  │  Stage 1:         │
  │  Vector Search    │     Fast, approximate
  │  (bi-encoder)     │     Retrieves top-20 candidates
  │  ~50ms            │
  └────────┬─────────┘
           │ top-20 candidates
           ▼
  ┌──────────────────┐
  │  Stage 2:         │
  │  Cross-Encoder    │     Slow, precise
  │  Reranking        │     Re-scores each (query, doc) pair
  │  ~200ms           │
  └────────┬─────────┘
           │ top-5 reranked
           ▼
  ┌──────────────────┐
  │  Return to Agent  │     High precision, manageable latency
  └──────────────────┘
```

**Why reranking helps:** Bi-encoders (embedding models) encode the query and document independently, then compare. Cross-encoders see the query and document together, enabling fine-grained token-level comparison. This catches subtle relevance signals that bi-encoders miss.

**V2+ feature.** Reranking adds latency (~200ms) but significantly improves Precision@k. The tradeoff is worthwhile when precision matters more than latency -- which is the case for medical applications.

### Query Expansion

**What it is:** Before searching, rephrase or expand the query to improve retrieval. Techniques include:

- **Synonym expansion:** "kidney" → "kidney OR renal OR nephric"
- **LLM-based rephrasing:** Ask the LLM to generate multiple search queries from a single question
- **Hypothetical Document Embeddings (HyDE):** Ask the LLM to generate what the ideal answer would look like, then embed that answer and use it as the search query

```
QUERY EXPANSION EXAMPLE:

Original query: "metformin renal dosing"

LLM-expanded queries:
  1. "metformin dose adjustment kidney function"
  2. "metformin eGFR threshold contraindication"
  3. "metformin renal impairment guidelines"

Each expanded query is searched independently.
Results are merged and deduplicated.
```

**V2+ feature.** Query expansion increases recall at the cost of additional embedding API calls and search latency. For the AI Doctor, the agent already performs a form of query expansion naturally -- it can make multiple tool calls with different queries across its turns.

### Agentic RAG Patterns

**What it is:** Instead of a fixed retrieval pipeline, the agent dynamically decides its search strategy. This is already partially implemented in the AI Doctor (the agent decides what and when to search), but more advanced patterns exist:

- **Iterative retrieval:** Search, read results, decide if more information is needed, search again with refined queries
- **Routing:** Based on the query, decide whether to use vector search, keyword search, or a specific filter
- **Self-evaluation:** After retrieval, the agent evaluates whether the results are sufficient before generating the answer

**This is the direction the AI Doctor is already heading.** With `max_turns=4`, the agent can search, evaluate results, and search again. Future iterations could add explicit routing logic (e.g., "for drug interactions, search the FDA label collection; for clinical management, search the guideline collection").

### V2+ Technique Summary

| Technique | What it adds | Complexity | Expected improvement |
|-----------|-------------|------------|---------------------|
| BM25 | Exact keyword matching | Medium | Better recall for specific drug names |
| Hybrid search (RRF) | Combined ranking | Medium | 5-15% better overall retrieval |
| Cross-encoder reranking | Precision boost | Medium | 10-20% better Precision@k |
| Query expansion | Better recall | Low-Medium | 5-10% better Recall@k |
| Agentic RAG routing | Dynamic strategy | High | Context-dependent improvement |

These are listed in approximate order of implementation priority. Hybrid search gives the most improvement for medical RAG (exact drug and lab terms), followed by reranking for precision.

---

## Next Steps

> **Next:** Proceed to [07-TOOL-USE-AND-AGENTIC-LOOP.md](./07-TOOL-USE-AND-AGENTIC-LOOP.md) to learn how the model calls functions and executes the agentic loop -- the pattern that powers the RAG tool integration you learned about in this module.

---

*Part 6 of 11: Agent Architecture & AI Model Internals Series*
*AI Doctor Assistant Project*
