# RAG Architecture and Pipeline

**Part 5 of 11: Agent Architecture & AI Model Internals Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Learning Objectives](#learning-objectives)
2. [What Is RAG and Why It Matters](#1-what-is-rag-and-why-it-matters)
3. [The Two Phases -- Ingest and Retrieve](#2-the-two-phases----ingest-and-retrieve)
4. [Document Parsing and Chunking](#3-document-parsing-and-chunking)
5. [The Retrieval Pipeline](#4-the-retrieval-pipeline)
6. [Agent-Tool RAG vs Preprocessing RAG](#5-agent-tool-rag-vs-preprocessing-rag)
7. [The Full Agent-Tool Flow](#6-the-full-agent-tool-flow)
8. [Formatting Results for the Agent](#7-formatting-results-for-the-agent)

---

## Learning Objectives

After reading this document, you will be able to:

- **Define** Retrieval-Augmented Generation and explain the four problems it solves: knowledge cutoff, hallucination, traceability, and domain specificity
- **Diagram** the two-phase RAG architecture -- offline ingestion and online retrieval -- and explain why they use different embedding task types
- **Explain** why structure-aware markdown parsing produces better chunks than naive text splitting
- **Trace** the retrieval pipeline step by step: embed query, search Qdrant, filter by metadata, apply score threshold, return results
- **Compare** preprocessing RAG (inject-then-generate) with agent-tool RAG (agent-decides-when-to-search) and articulate why the AI Doctor chose the latter
- **Walk through** the full multi-turn agent-tool flow with `max_turns=4`, explaining what the agent does at each turn
- **Describe** the XML formatting pattern for search results and explain why XML is effective for LLM consumption
- **Map** each concept to actual code in the AI Doctor codebase: `document_processor.py`, `rag_service.py`, `briefing_agent.py`, `tools.py`

Key mental models to internalize:

- **RAG is two systems stitched together.** The ingestion pipeline and the retrieval pipeline are fundamentally different workloads (batch vs real-time, write path vs read path). Design them separately.
- **Chunking is a retrieval problem, not a storage problem.** The question is not "how do I split this document?" but "what chunk boundaries will produce the best search results for the queries my users will ask?"
- **The agent is the retrieval strategist.** In agent-tool RAG, the LLM decides what to search, when to search again, and when it has enough context. You are delegating retrieval strategy to the model, not hardcoding it.

Common misconceptions this document addresses:

- "RAG is just putting documents in the prompt." -- That is preprocessing RAG. Agent-tool RAG is fundamentally different: the agent controls retrieval.
- "Bigger chunks are better because they have more context." -- Bigger chunks dilute relevance scores and waste context window tokens on irrelevant text.
- "You embed the query and documents the same way." -- Embedding models use different task types (`RETRIEVAL_QUERY` vs `RETRIEVAL_DOCUMENT`) that optimize the vector space differently.
- "RAG eliminates hallucination." -- RAG reduces hallucination by providing source material, but the model can still misinterpret or ignore the retrieved context.

---

## 1. What Is RAG and Why It Matters

### The Fundamental Problem

Language models are trained on a fixed dataset at a fixed point in time. Once training ends, the model's knowledge is frozen. It knows what it learned during pre-training and alignment -- nothing more. If a clinical guideline was published after the training cutoff, the model has never seen it. If your organization has proprietary treatment protocols, the model knows nothing about them. If a drug interaction was recently discovered, the model will not warn about it.

This is not a flaw. It is a consequence of how language models work (covered in Doc 03). Pre-training produces a static set of weights. Those weights encode the statistical patterns of the training data. There is no mechanism for the weights to update themselves when new information becomes available.

**Retrieval-Augmented Generation (RAG)** solves this by adding a retrieval step before generation. Instead of relying solely on the model's internal knowledge, you search an external knowledge base for relevant information and include it in the prompt. The model generates its response grounded in the retrieved context rather than from memory alone.

The pattern is simple:

```
┌──────────┐      ┌───────────────┐      ┌──────────────┐
│          │      │               │      │              │
│  Query   ├─────►│   Retrieve    ├─────►│   Augment    │
│          │      │  (search KB)  │      │  (add to     │
└──────────┘      └───────────────┘      │   prompt)    │
                                         └──────┬───────┘
                                                │
                                         ┌──────▼───────┐
                                         │              │
                                         │   Generate   │
                                         │  (LLM call)  │
                                         │              │
                                         └──────────────┘
```

**Retrieve** relevant documents from a knowledge base. **Augment** the prompt by adding those documents as context. **Generate** a response grounded in that context. That is RAG in three words.

### The Four Problems RAG Solves

**1. Knowledge Cutoff**

The model's training data has a fixed end date. Anything published, updated, or changed after that date is invisible to the model. For clinical guidelines, this is dangerous -- medical recommendations change frequently. The ADA Standards of Care are updated annually. Drug safety alerts can be issued at any time.

RAG sidesteps the cutoff entirely. Your knowledge base is updated independently of the model. When a new guideline is published, you ingest it into the vector database. The next query that matches it will retrieve the current recommendation, not a stale one from the training data.

**2. Hallucination**

When a model does not know the answer, it does not say "I don't know." It generates a plausible-sounding response based on statistical patterns. This is hallucination. In medicine, a hallucinated drug dosage or a fabricated contraindication can be harmful.

RAG reduces hallucination by providing the model with source material to reference. Instead of generating from memory, the model can quote or paraphrase the retrieved text. This does not eliminate hallucination -- the model can still misinterpret or ignore the context -- but it dramatically reduces the likelihood by giving the model correct information to work with.

**3. Traceability and Citations**

When a model generates a response from its internal knowledge, there is no way to verify where the information came from. You cannot trace a claim back to a specific source. This makes it impossible to audit, verify, or challenge the response.

RAG enables citations. Every retrieved chunk comes from a specific document, section, and page. The model can cite its sources: "According to the ADA Standards of Care [1], the target HbA1c for most adults is below 7%." The physician can then verify the claim against the cited guideline.

**4. Domain-Specific Knowledge**

General-purpose models are trained on public internet data. They have broad knowledge but shallow depth in specialized domains. Your organization's internal treatment protocols, formulary restrictions, and institutional guidelines are not in the training data. They cannot be, because they are proprietary.

RAG lets you inject domain-specific knowledge at query time. You build a knowledge base from your own documents and the model uses those documents as its primary reference. The model's general medical knowledge provides a foundation, but the specific recommendations come from your curated guideline database.

```
AI DOCTOR EXAMPLE:
The AI Doctor's knowledge base contains clinical practice guidelines --
ADA Standards of Care for diabetes, KDIGO guidelines for chronic
kidney disease, ACC/AHA guidelines for hypertension. These documents
are structured, authoritative, and frequently updated.

When the agent generates a briefing for Maria Garcia (Type 2 Diabetes,
Hypertension, CKD Stage 3), it does not rely on Claude's training
data for treatment recommendations. It searches the guideline database
for "metformin dosing in CKD stage 3" and "blood pressure targets
diabetic nephropathy" and grounds its flags and actions in the
retrieved evidence.

Without RAG, the agent might recommend a metformin dose that is
contraindicated at her eGFR level. With RAG, it retrieves the
specific KDIGO recommendation for renal dosing adjustments.
```

### RAG Is Not Fine-Tuning

A common confusion: why not just fine-tune the model on your guidelines?

Fine-tuning changes the model's weights. It bakes knowledge into the model itself. This has several drawbacks for frequently-updated domain knowledge:

| Aspect | Fine-Tuning | RAG |
|--------|-------------|-----|
| **Update speed** | Re-train the model (hours/days) | Re-index documents (minutes) |
| **Cost** | GPU compute for training | Embedding API calls + vector DB storage |
| **Traceability** | None -- knowledge is in weights | Full -- every fact traces to a source document |
| **Freshness** | Stale until next training run | Current as of last ingestion |
| **Hallucination** | Can still hallucinate fine-tuned facts | Model can reference retrieved text directly |
| **Multi-tenancy** | Separate model per tenant | Separate collection/filter per tenant |

Fine-tuning is the right tool for teaching a model new behaviors, styles, or formats. RAG is the right tool for giving a model access to a body of knowledge that changes over time.

---

## 2. The Two Phases -- Ingest and Retrieve

RAG is two separate systems that share a vector database. They run at different times, have different performance requirements, and use different embedding configurations. Understanding this separation is critical for building a reliable RAG pipeline.

### Phase 1: Ingestion (Offline / Batch)

Ingestion is the write path. It takes raw documents, processes them into chunks, embeds each chunk into a vector, and stores the vectors in a database. This happens ahead of time -- when you add a new guideline, not when a user asks a question.

```
  INGESTION PIPELINE (offline, batch)
  ====================================

  ┌──────────────────┐
  │  Raw Documents   │
  │  (.md files)     │
  │                  │
  │  - ADA Standards │
  │  - KDIGO Guide   │
  │  - ACC/AHA Guide │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  Parse           │
  │                  │
  │  Markdown ->     │
  │  Sections with   │
  │  heading paths   │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  Chunk           │
  │                  │
  │  Sections ->     │
  │  DocumentChunks  │
  │  (max 800 tokens)│
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  Embed           │     task_type = RETRIEVAL_DOCUMENT
  │                  │
  │  text-embedding  │     "This text IS a document
  │  -005 (768 dim)  │      that will be searched"
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  Store           │
  │                  │
  │  Qdrant vector   │
  │  DB (cosine      │
  │  similarity)     │
  └──────────────────┘
```

Each step has a specific job:

1. **Parse** -- Read the raw document and extract structure. For markdown, this means identifying headings, their levels, and the body text under each heading. The output is a list of `Section` objects, each with a heading, level, body, and path through the heading hierarchy.

2. **Chunk** -- Convert sections into chunks that are small enough for the embedding model to handle effectively and large enough to carry meaningful context. Each chunk is prefixed with its section path (e.g., `[Diabetes Management > Pharmacologic Therapy > Metformin]`) to give the embedding model richer context about what the chunk is about.

3. **Embed** -- Convert each chunk's text into a dense vector using an embedding model. The AI Doctor uses Google's `text-embedding-005` model at 768 dimensions. The task type is `RETRIEVAL_DOCUMENT` because these vectors represent documents that will be searched.

4. **Store** -- Write the vectors and their metadata into Qdrant, a vector database. Each point in Qdrant contains the vector, the chunk text, and structured metadata (document ID, specialty, conditions, drugs, section path).

### Phase 2: Retrieval (Online / Per-Query)

Retrieval is the read path. It takes a user query, embeds it, searches the vector database for similar vectors, and returns the matching chunks. This happens in real time, during the agent's execution.

```
  RETRIEVAL PIPELINE (online, per-query)
  =======================================

  ┌──────────────────┐
  │  Query           │
  │                  │
  │  "metformin      │
  │   contraindica-  │
  │   tions CKD"     │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  Embed Query     │     task_type = RETRIEVAL_QUERY
  │                  │
  │  text-embedding  │     "This text is a QUERY
  │  -005 (768 dim)  │      that will search documents"
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  Search Qdrant   │
  │                  │     cosine similarity
  │  - Filter:       │     score_threshold >= 0.5
  │    specialty =   │     limit = 5
  │    "nephrology"  │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  Format Results  │
  │                  │
  │  -> XML with     │
  │  source IDs,     │
  │  scores, text    │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  Send to Agent   │
  │                  │
  │  Agent uses      │
  │  results to      │
  │  generate        │
  │  briefing        │
  └──────────────────┘
```

### Why Different Task Types?

This is a critical detail. Doc 04 (Embeddings) explains how embedding models are trained for asymmetric retrieval. When you embed a document, the embedding model optimizes the vector to represent *what the document is about*. When you embed a query, it optimizes the vector to represent *what the user is looking for*. These are different tasks that produce different vector distributions.

The AI Doctor uses Google's `text-embedding-005` model with two task types:

| Phase | Task Type | Purpose |
|-------|-----------|---------|
| Ingestion | `RETRIEVAL_DOCUMENT` | "This text is a document. Encode what it is about." |
| Retrieval | `RETRIEVAL_QUERY` | "This text is a search query. Encode what it is looking for." |

From `rag_service.py`, you can see this clearly:

```python
# Ingestion: embed documents for storage
def embed_batch(texts: list[str]) -> list[list[float]]:
    response = client.models.embed_content(
        model=settings.embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(
            output_dimensionality=settings.embedding_dimensions,
            task_type="RETRIEVAL_DOCUMENT",    # <-- document task type
        ),
    )

# Retrieval: embed query for search
def embed_text(text: str) -> list[float]:
    response = client.models.embed_content(
        model=settings.embedding_model,
        contents=[text],
        config=types.EmbedContentConfig(
            output_dimensionality=settings.embedding_dimensions,
            task_type="RETRIEVAL_QUERY",       # <-- query task type
        ),
    )
```

If you use `RETRIEVAL_DOCUMENT` for both ingestion and retrieval, your search results will be worse. The model was trained to map queries to documents, not documents to documents. Using the correct task type for each phase is a low-effort, high-impact optimization.

```
AI DOCTOR EXAMPLE:
Consider the query "metformin dose adjustment for eGFR 45".

With RETRIEVAL_QUERY, the embedding captures the intent: "I want to know
about adjusting metformin dose when kidney function is reduced."

With RETRIEVAL_DOCUMENT, the same text would be embedded as if it were
a document passage, missing the query-intent optimization.

The RETRIEVAL_DOCUMENT embedding of the chunk "[KDIGO > CKD > Drug Dosing]
Reduce metformin to 500mg twice daily when eGFR is 30-45 mL/min" is
optimized to represent what the passage IS ABOUT.

Cosine similarity between the query vector and the document vector is
highest when both were embedded with the correct task type.
```

---

## 3. Document Parsing and Chunking

Chunking is the most impactful decision in a RAG pipeline. Get it wrong and no amount of embedding quality or search tuning will save you. Get it right and even a simple retrieval pipeline will produce good results.

### Why Structure-Aware Parsing Matters

The naive approach to chunking is: split the document into fixed-size windows of N tokens with M tokens of overlap. This is what many tutorials and frameworks default to. It is simple. It is also terrible for structured documents.

Consider a clinical guideline:

```markdown
# Diabetes Management

## Pharmacologic Therapy

### Metformin

Metformin is the preferred first-line agent for type 2 diabetes.
Start at 500mg once daily, increase to 1000mg twice daily.

**Contraindications:**
- eGFR < 30 mL/min: Discontinue
- eGFR 30-45 mL/min: Reduce dose to 500mg twice daily
- Lactic acidosis risk increases with renal impairment

### Sulfonylureas

Sulfonylureas are second-line agents when metformin is insufficient.
```

Naive chunking with a 200-token window might produce:

```
Chunk 1: "...type 2 diabetes. Start at 500mg once daily, increase
          to 1000mg twice daily. Contraindications: eGFR < 30..."
Chunk 2: "...mL/min: Discontinue. eGFR 30-45 mL/min: Reduce dose
          to 500mg twice daily. Lactic acidosis risk increases..."
```

What is wrong with this? The chunks have **lost their heading context**. When chunk 2 is retrieved, the embedding model sees "Reduce dose to 500mg twice daily" but does not know this is about metformin, or that it falls under the contraindications section, or that the broader topic is diabetes management. The section path -- the hierarchy that gives the text its meaning -- has been destroyed.

Structure-aware parsing preserves this hierarchy:

```
Chunk 1: "[Diabetes Management > Pharmacologic Therapy > Metformin]
          Metformin is the preferred first-line agent for type 2 diabetes.
          Start at 500mg once daily, increase to 1000mg twice daily.
          Contraindications:
          - eGFR < 30 mL/min: Discontinue
          - eGFR 30-45 mL/min: Reduce dose to 500mg twice daily
          - Lactic acidosis risk increases with renal impairment"
```

The entire metformin section, including its heading path, is a single chunk. When the agent searches for "metformin renal dosing," this chunk will have a high similarity score because the embedding captures both the section context and the content.

### How document_processor.py Works

The AI Doctor's document processor has two stages: parse and chunk. Let us trace through each.

#### Stage 1: parse_markdown()

`parse_markdown()` reads a markdown document and extracts sections, preserving the heading hierarchy as a path.

```python
# From backend/src/services/document_processor.py

class Section:
    """A markdown section with heading hierarchy and body text."""

    def __init__(self, heading: str, level: int, body: str, path: list[str]) -> None:
        self.heading = heading
        self.level = level
        self.body = body
        self.path = path  # e.g. ["Diabetes Management", "Pharmacologic Therapy", "Metformin"]


def parse_markdown(text: str) -> list[Section]:
    """Parse markdown text into sections preserving heading hierarchy."""
    lines = text.split("\n")
    sections: list[Section] = []
    heading_stack: list[str] = []  # tracks current heading at each level
    current_heading = ""
    current_level = 0
    current_body_lines: list[str] = []

    def _flush() -> None:
        body = "\n".join(current_body_lines).strip()
        if body or current_heading:
            path = list(heading_stack)
            sections.append(Section(
                heading=current_heading,
                level=current_level,
                body=body,
                path=path,
            ))

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            _flush()
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()

            # Update heading stack: trim to current level, then set
            heading_stack = heading_stack[:level - 1]
            while len(heading_stack) < level - 1:
                heading_stack.append("")
            heading_stack.append(heading)

            current_heading = heading
            current_level = level
            current_body_lines = []
        else:
            current_body_lines.append(line)

    _flush()
    return sections
```

The key data structure is `heading_stack`. It tracks the current position in the heading hierarchy. When a `## Pharmacologic Therapy` heading is encountered inside a `# Diabetes Management` section, the stack becomes `["Diabetes Management", "Pharmacologic Therapy"]`. When a `### Metformin` heading follows, it becomes `["Diabetes Management", "Pharmacologic Therapy", "Metformin"]`.

This is how `path` is built. Every section knows exactly where it sits in the document hierarchy.

Let us trace through a concrete example:

```
Input markdown:
  # Diabetes Management
  ## Pharmacologic Therapy
  ### Metformin
  Metformin is the preferred first-line agent.
  ### Sulfonylureas
  Sulfonylureas are second-line agents.
  ## Non-Pharmacologic Therapy
  Diet and exercise remain foundational.
```

The parser produces:

```
Section(heading="Metformin",        level=3,
        path=["Diabetes Management", "Pharmacologic Therapy", "Metformin"],
        body="Metformin is the preferred first-line agent.")

Section(heading="Sulfonylureas",    level=3,
        path=["Diabetes Management", "Pharmacologic Therapy", "Sulfonylureas"],
        body="Sulfonylureas are second-line agents.")

Section(heading="Non-Pharmacologic Therapy", level=2,
        path=["Diabetes Management", "Non-Pharmacologic Therapy"],
        body="Diet and exercise remain foundational.")
```

Notice how the heading stack is trimmed when the heading level decreases. When we encounter `## Non-Pharmacologic Therapy` (level 2), the stack is trimmed from `["Diabetes Management", "Pharmacologic Therapy", "Sulfonylureas"]` back to `["Diabetes Management"]` and then `"Non-Pharmacologic Therapy"` is appended.

#### Stage 2: chunk_sections()

`chunk_sections()` converts parsed sections into `DocumentChunk` objects suitable for embedding and storage. It handles two critical tasks: prefixing chunks with their section path, and splitting oversized sections at paragraph boundaries.

```python
# From backend/src/services/document_processor.py

def chunk_sections(
    sections: list[Section],
    *,
    max_tokens: int = 800,
    document_id: str = "",
    document_title: str = "",
    specialty: str = "",
    document_type: str = "clinical_guideline",
    conditions: list[str] | None = None,
    drugs: list[str] | None = None,
    publication_date: date | None = None,
) -> list[DocumentChunk]:
    """Convert parsed sections into DocumentChunks with section path prefix."""
    raw_chunks: list[tuple[str, str]] = []  # (section_path, text)

    for section in sections:
        if not section.body:
            continue

        section_path = " > ".join(p for p in section.path if p)
        prefix = f"[{section_path}] " if section_path else ""
        full_text = prefix + section.body

        if _estimate_tokens(full_text) <= max_tokens:
            raw_chunks.append((section_path, full_text))
        else:
            # Split at paragraph boundaries
            paragraphs = re.split(r"\n\n+", section.body)
            current_parts: list[str] = []
            current_size = _estimate_tokens(prefix)

            for para in paragraphs:
                para_tokens = _estimate_tokens(para)
                if current_size + para_tokens > max_tokens and current_parts:
                    raw_chunks.append(
                        (section_path, prefix + "\n\n".join(current_parts))
                    )
                    current_parts = []
                    current_size = _estimate_tokens(prefix)
                current_parts.append(para)
                current_size += para_tokens

            if current_parts:
                raw_chunks.append(
                    (section_path, prefix + "\n\n".join(current_parts))
                )

    total = len(raw_chunks)
    return [
        DocumentChunk(
            text=text,
            document_id=document_id,
            document_title=document_title,
            section_path=section_path,
            specialty=specialty,
            document_type=document_type,
            conditions=conditions or [],
            drugs=drugs or [],
            publication_date=publication_date,
            chunk_index=idx,
            total_chunks=total,
        )
        for idx, (section_path, text) in enumerate(raw_chunks)
    ]
```

### The Section Path Prefix

The most important line in `chunk_sections()` is this:

```python
prefix = f"[{section_path}] " if section_path else ""
full_text = prefix + section.body
```

This prepends the heading hierarchy to the chunk text before embedding. A chunk body of "Reduce dose to 500mg twice daily when eGFR is 30-45 mL/min" becomes:

```
[Diabetes Management > Pharmacologic Therapy > Metformin] Reduce dose to
500mg twice daily when eGFR is 30-45 mL/min
```

When this text is embedded, the embedding model sees the full context. The vector now encodes not just "dose reduction" but "metformin dose reduction in the context of diabetes pharmacologic therapy." This dramatically improves retrieval quality for queries like "metformin renal dosing" or "CKD dose adjustments."

### The 800-Token Maximum and Paragraph-Boundary Splits

Why 800 tokens? It is a balance between two competing forces:

- **Too small** (< 200 tokens): Chunks lack sufficient context. A sentence fragment about dose reduction without the surrounding context about when and why is not useful.
- **Too large** (> 1500 tokens): Chunks dilute the relevance signal. If a 2000-token chunk contains one paragraph about metformin dosing and five paragraphs about monitoring, the embedding will be a vague average of all topics. A query about metformin dosing will get a mediocre similarity score.

800 tokens is approximately 600 words -- enough for a complete subsection of a clinical guideline, but small enough that the embedding captures a focused topic.

When a section exceeds 800 tokens, `chunk_sections()` splits at paragraph boundaries (`\n\n`). This is better than splitting mid-sentence because paragraphs are natural units of thought. The section path prefix is repeated on every split chunk so no chunk loses its hierarchical context.

```
  CHUNKING A LONG SECTION
  ========================

  Section: "Diabetes Management > Pharmacologic Therapy > Metformin"
  Body: 1200 tokens across 4 paragraphs

  ┌─────────────────────────────────────────┐
  │ [Diabetes > Pharmacologic > Metformin]  │
  │                                         │
  │ Paragraph 1 (300 tokens)               │
  │ First-line agent, dosing schedule...    │
  │                                         │
  │ Paragraph 2 (250 tokens)               │
  │ Contraindications and precautions...    │
  │                                         │  Total: 1200 tokens
  │ Paragraph 3 (350 tokens)               │  Exceeds 800 max
  │ Monitoring and lab requirements...      │
  │                                         │
  │ Paragraph 4 (300 tokens)               │
  │ Special populations, elderly dosing...  │
  └─────────────────────────────────────────┘

                    │
                    ▼  Split at paragraph boundary

  ┌──────────────────────────┐  ┌──────────────────────────┐
  │ [Diabetes > Pharma >     │  │ [Diabetes > Pharma >     │
  │  Metformin]              │  │  Metformin]              │
  │                          │  │                          │
  │ Paragraph 1 (300 tokens) │  │ Paragraph 3 (350 tokens) │
  │ Paragraph 2 (250 tokens) │  │ Paragraph 4 (300 tokens) │
  │                          │  │                          │
  │ Chunk 0/2 (~580 tokens)  │  │ Chunk 1/2 (~680 tokens)  │
  └──────────────────────────┘  └──────────────────────────┘

  Both chunks retain the [section path] prefix.
  Both chunks respect paragraph boundaries.
```

### Token Estimation

The processor uses a simple heuristic for token estimation:

```python
def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return len(text) // 4
```

This is intentionally approximate. The actual tokenizer for `text-embedding-005` is not exposed via the API, and calling a tokenizer for every chunking decision would be slow. The 4-characters-per-token ratio is a well-known approximation for English text that is close enough for chunking decisions. Being off by 10-20% on chunk size is acceptable -- the 800-token limit is itself a heuristic, not a hard boundary.

### The DocumentChunk Model

Each chunk is stored as a `DocumentChunk` with rich metadata:

```python
# From backend/src/models/rag.py

class DocumentChunk(BaseModel):
    """A chunk of a clinical guideline document with metadata for vector storage."""

    text: str                    # The chunk text (with section path prefix)
    document_id: str             # Source document identifier
    document_title: str          # Human-readable document name
    section_path: str            # "Diabetes > Pharmacologic > Metformin"
    specialty: str               # "endocrinology", "nephrology", etc.
    document_type: str           # "clinical_guideline"
    conditions: list[str]        # ["Type 2 Diabetes", "CKD"]
    drugs: list[str]             # ["Metformin", "Insulin"]
    publication_date: date       # For freshness ranking
    chunk_index: int             # Position within document (0-based)
    total_chunks: int            # Total chunks from this document
```

This metadata serves two purposes:

1. **Filtering** -- Qdrant indexes the `specialty`, `conditions`, `drugs`, and `document_type` fields. The search query can filter by specialty before computing similarity, which narrows the search space and improves relevance.

2. **Citation** -- When the agent cites a source, the `document_title`, `section_path`, and `source_id` tell the physician exactly where the information came from. "ADA Standards of Care, Pharmacologic Therapy > Metformin, source [2]" is verifiable.

```
AI DOCTOR EXAMPLE:
When the ADA Standards of Care document is ingested with:

    document_id="ada-standards-2024"
    document_title="ADA Standards of Medical Care in Diabetes"
    specialty="endocrinology"
    conditions=["Type 2 Diabetes", "Type 1 Diabetes"]
    drugs=["Metformin", "Insulin", "GLP-1 RA", "SGLT2i"]

...each chunk inherits these metadata fields. A search filtered to
specialty="endocrinology" will only search ADA and other endocrinology
guidelines, skipping cardiology and nephrology documents entirely.
This is faster (smaller search space) and more relevant (no off-topic results).
```

---

## 4. The Retrieval Pipeline

The retrieval pipeline is what runs at query time -- when the agent decides it needs to search for clinical guidelines. It is a focused, four-step process that transforms a text query into a ranked list of relevant chunks.

### Step-by-Step Walkthrough

Let us trace the full retrieval path for the query `"metformin contraindications CKD"` with `specialty="nephrology"`:

**Step 1: Embed the query**

```python
# From backend/src/services/rag_service.py

def embed_text(text: str) -> list[float]:
    """Embed a single text string for query-time search."""
    if settings.google_api_key:
        vectors = _vertex_embed_via_api_key([text], "RETRIEVAL_QUERY")
        vector = vectors[0]
    else:
        client = get_genai_client()
        response = client.models.embed_content(
            model=settings.embedding_model,
            contents=[text],
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dimensions,
                task_type="RETRIEVAL_QUERY",
            ),
        )
        vector = list(response.embeddings[0].values)
    return vector
```

The query text `"metformin contraindications CKD"` is sent to `text-embedding-005` with task type `RETRIEVAL_QUERY`. The model returns a 768-dimensional vector that represents the *intent* of the query.

**Step 2: Search Qdrant with optional filter**

```python
def search(
    query: str,
    specialty: str | None = None,
    limit: int = 5,
) -> list[RetrievalResult]:
    """Embed query, search Qdrant, return scored results."""
    query_vector = embed_text(query)

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
        query_filter=query_filter,
        score_threshold=0.5,
        limit=limit,
        with_payload=True,
    )
```

Several things happen here:

1. The query vector is sent to Qdrant's `query_points` endpoint.
2. If `specialty="nephrology"` is provided, Qdrant first filters the collection to only include points where the `specialty` payload field matches `"nephrology"`. This is a **pre-filter** -- it narrows the candidate set before computing cosine similarity.
3. Qdrant computes cosine similarity between the query vector and every remaining candidate vector.
4. Only results with a score >= 0.5 are returned (`score_threshold=0.5`).
5. Results are limited to the top 5 (`limit=5`), ordered by descending similarity score.

**Step 3: Apply score threshold (>= 0.5)**

The score threshold is the minimum cosine similarity required for a result to be returned. Cosine similarity ranges from -1 to 1, where 1 is identical and 0 is unrelated.

A threshold of 0.5 is moderate -- it filters out clearly irrelevant results while allowing partial matches through. For example:

| Score | Interpretation | Passes? |
|-------|---------------|---------|
| 0.85 | Strong semantic match | Yes |
| 0.72 | Good match, related topic | Yes |
| 0.55 | Partial match, tangentially related | Yes |
| 0.48 | Weak match, mostly unrelated | No |
| 0.30 | Essentially unrelated | No |

Why not set the threshold higher? Because the agent can evaluate relevance itself. A chunk with a 0.55 score might contain a crucial piece of information in a paragraph the embedding model did not fully capture. By keeping the threshold moderate and returning up to 5 results, we let the agent (the LLM) make the final relevance judgment. The vector search is a coarse filter; the LLM is the fine filter.

**Step 4: Build RetrievalResult objects**

```python
# From backend/src/services/rag_service.py

retrieval_results = []
for idx, point in enumerate(results.points):
    payload = point.payload
    chunk = DocumentChunk(
        text=payload["text"],
        document_id=payload["document_id"],
        document_title=payload["document_title"],
        section_path=payload["section_path"],
        specialty=payload["specialty"],
        document_type=payload["document_type"],
        conditions=payload["conditions"],
        drugs=payload["drugs"],
        publication_date=payload["publication_date"],
        chunk_index=payload["chunk_index"],
        total_chunks=payload["total_chunks"],
    )
    retrieval_results.append(
        RetrievalResult(chunk=chunk, score=point.score, source_id=idx + 1)
    )
```

Each result is wrapped in a `RetrievalResult` that pairs the `DocumentChunk` with its similarity `score` and a sequential `source_id` (1, 2, 3...) used for citation. The agent will later reference these as `[1]`, `[2]`, etc. in its generated text.

### The Async Variant

The search function also has an async variant (`async_search`) for use inside the agent tool handler. The tool handler runs inside the Claude Agent SDK's agentic loop, which is async. Using a sync Qdrant client inside an async handler would block the event loop.

```python
# From backend/src/services/rag_service.py

async def async_search(
    query: str,
    specialty: str | None = None,
    limit: int = 5,
) -> list[RetrievalResult]:
    """Embed query and search Qdrant asynchronously (non-blocking)."""
    query_vector = await async_embed_text(query)

    client = get_async_qdrant_client()
    results = await client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=query_filter,
        score_threshold=0.5,
        limit=limit,
        with_payload=True,
    )
```

The logic is identical to the sync version. The only differences are:
- `await async_embed_text(query)` instead of `embed_text(query)`
- `get_async_qdrant_client()` returns `AsyncQdrantClient` instead of `QdrantClient`
- `await client.query_points(...)` instead of `client.query_points(...)`

This is a common pattern in async Python: every I/O call that could block must be awaited. The sync version is used during ingestion (a batch script). The async version is used during retrieval (inside the FastAPI request handler and agent tool loop).

```
AI DOCTOR EXAMPLE:
When the agent searches for "metformin contraindications CKD" with
specialty="nephrology", the retrieval pipeline:

1. Embeds the query with RETRIEVAL_QUERY -> 768-dim vector
2. Filters Qdrant to nephrology-specialty chunks only
3. Computes cosine similarity against filtered candidates
4. Returns top 5 results with score >= 0.5

A typical result set might look like:
  [1] score=0.82 "KDIGO > CKD > Drug Dosing"     -> metformin renal adjustments
  [2] score=0.75 "ADA > Pharmacologic > Metformin" -> general contraindications
  [3] score=0.68 "KDIGO > CKD > Monitoring"       -> eGFR monitoring schedule
  [4] score=0.61 "ADA > Comorbidities > CKD"      -> diabetes + CKD overview
  [5] score=0.54 "KDIGO > CKD > ACE Inhibitors"   -> renal-protective agents

The agent receives all 5, evaluates their relevance to the specific
patient (Maria Garcia, eGFR 45), and cites [1] and [2] in the briefing.
```

### Qdrant Collection Setup

Before search works, the collection must exist with the right configuration. The `ensure_collection()` function in `rag_service.py` handles this:

```python
def ensure_collection() -> None:
    """Create the Qdrant collection if it doesn't exist."""
    client = get_qdrant_client()
    collections = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in collections:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,  # 768
                distance=Distance.COSINE,
            ),
        )
        # Create payload indexes for filtering
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

Three things to note:

1. **Vector size matches embedding dimensions.** The collection is created with `size=768` to match `text-embedding-005` at 768 dimensions. A mismatch here would cause an error on upsert.

2. **Cosine distance.** The collection uses `Distance.COSINE`, which matches the similarity metric the embedding model was trained with. Using Euclidean distance would produce different (worse) rankings.

3. **Payload indexes.** Five fields are indexed as `KEYWORD` type. This enables fast pre-filtering. Without indexes, Qdrant would have to scan every point's payload to apply filters, which is O(n). With indexes, filtering is O(log n) or better.

---

## 5. Agent-Tool RAG vs Preprocessing RAG

There are two fundamentally different ways to integrate retrieval into an LLM application. Understanding the distinction is essential because it determines the architecture of the entire system.

### Approach 1: Preprocessing RAG

Preprocessing RAG retrieves context *before* calling the LLM. Your application code performs the search, formats the results, and injects them into the system prompt or user message. The LLM never knows a search happened -- it just sees extra context in its prompt.

```
  PREPROCESSING RAG
  =================

  ┌────────────┐     ┌──────────────┐     ┌──────────────┐     ┌───────────┐
  │            │     │              │     │              │     │           │
  │  User      ├────►│  Your Code   ├────►│  Search      ├────►│  Format   │
  │  Query     │     │  (retrieval  │     │  Qdrant      │     │  Results  │
  │            │     │   logic)     │     │              │     │           │
  └────────────┘     └──────────────┘     └──────────────┘     └─────┬─────┘
                                                                     │
                                                                     ▼
                     ┌──────────────┐     ┌──────────────────────────────────┐
                     │              │     │  System Prompt:                  │
                     │  LLM Call    │◄────│  "Here are relevant guidelines:" │
                     │  (single     │     │  + formatted search results      │
                     │   turn)      │     │  + user query                    │
                     │              │     └──────────────────────────────────┘
                     └──────┬───────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  Response    │
                     │  (grounded   │
                     │   in context)│
                     └──────────────┘
```

**Advantages:**
- Simple to implement. No tools, no agentic loop, no multi-turn complexity.
- Predictable. You control exactly what the LLM sees. One search, one LLM call, one response.
- Fast. Fewer API calls, lower latency.

**Disadvantages:**
- **Fixed retrieval strategy.** You decide what to search before you know what the LLM will need. If the query is ambiguous, you guess wrong.
- **One shot.** There is no opportunity to refine the search. If the first search returns irrelevant results, the LLM works with what it has.
- **Query construction is on you.** Your code must translate the user's input into an effective search query. For a complex patient with diabetes, CKD, and hypertension, what do you search for? All three at once? Each separately? Your code must make that decision.
- **Wastes context on irrelevant results.** If you search broadly to be safe, many retrieved chunks will be irrelevant to the specific question. Every irrelevant chunk wastes context window tokens.

### Approach 2: Agent-Tool RAG (What We Use)

Agent-tool RAG gives the LLM a search tool and lets it decide when, what, and how many times to search. The LLM is the retrieval strategist. It examines the patient data, formulates specific queries, evaluates results, and searches again if needed.

```
  AGENT-TOOL RAG
  ==============

  ┌────────────┐     ┌──────────────┐
  │            │     │              │
  │  User      ├────►│  Agent       │
  │  Query     │     │  (LLM with   │
  │            │     │   tools)     │
  └────────────┘     └──────┬───────┘
                            │
                     Turn 1 │  Agent examines patient data
                            │  Decides: "I need diabetes guidelines"
                            │
                            ▼
                     ┌──────────────┐
                     │  Tool Call:  │     ┌──────────────┐
                     │  search(     ├────►│  Qdrant      │
                     │   "metformin │     │  Search      │
                     │    renal     │     └──────┬───────┘
                     │    dosing")  │            │
                     └──────┬───────┘            │
                            │◄───────────────────┘
                            │  Results returned to agent
                     Turn 2 │
                            │  Agent evaluates results
                            │  Decides: "I also need CKD staging criteria"
                            │
                            ▼
                     ┌──────────────┐
                     │  Tool Call:  │     ┌──────────────┐
                     │  search(     ├────►│  Qdrant      │
                     │   "CKD stage │     │  Search      │
                     │    3 BP      │     └──────┬───────┘
                     │    targets") │            │
                     └──────┬───────┘            │
                            │◄───────────────────┘
                            │  Results returned to agent
                     Turn 3 │
                            │  Agent has enough context
                            │  Generates final briefing
                            │
                            ▼
                     ┌──────────────┐
                     │  Response    │
                     │  (grounded,  │
                     │   multi-     │
                     │   source)    │
                     └──────────────┘
```

**Advantages:**
- **Adaptive retrieval.** The LLM formulates queries based on what it sees in the patient data. It does not search for CKD guidelines unless the patient has CKD.
- **Multi-step refinement.** If the first search returns partial information, the agent can refine its query and search again. "Metformin dosing" can be followed by "metformin renal dose adjustment eGFR 45" if the first results were too general.
- **Domain-appropriate queries.** The LLM understands medical terminology. It can formulate queries like "HbA1c target elderly patients with CKD comorbidity" that a simple keyword extraction would miss.
- **Selective retrieval.** The agent only searches when it needs to. For a healthy patient with no concerning labs, it might skip the search entirely and generate a brief "all within normal limits" response.

**Disadvantages:**
- More complex to implement. Requires tool definitions, an agentic loop, multi-turn message handling.
- Higher latency. Each tool call is an additional API round trip (embed + search + format + return to LLM).
- Less predictable. The agent might search zero times, once, or four times. Debugging requires tracing through multiple turns.

### Why the AI Doctor Chose Agent-Tool RAG

The AI Doctor chose agent-tool RAG because of the nature of clinical briefings:

1. **Patients have multiple conditions.** Maria Garcia has diabetes, hypertension, and CKD. A preprocessing approach would need to search for all three, plus drug interactions, plus screening guidelines. That is five or more searches, many of which might be unnecessary for this specific visit. The agent can prioritize: it searches diabetes guidelines first (the visit reason), then CKD guidelines (eGFR is abnormal), and skips hypertension guidelines if the blood pressure is only mildly elevated.

2. **Queries are context-dependent.** The right search query depends on the patient's specific values. "Metformin dosing" is too vague. "Metformin dose adjustment for eGFR 45 in CKD stage 3" is specific and will return more relevant results. The agent sees the patient's eGFR of 45 and formulates the query accordingly.

3. **The agent can evaluate and re-search.** If the first search returns a general overview of metformin but not the specific renal dosing table, the agent can search again with a more specific query. This iterative refinement is impossible with preprocessing RAG.

4. **Citation accuracy.** Because the agent sees the source IDs and document titles of retrieved chunks, it can cite them precisely. In preprocessing RAG, the LLM sees a block of context and has to figure out which part came from which source.

```
AI DOCTOR EXAMPLE:
Preprocessing RAG for Maria Garcia might look like:

  search("Type 2 Diabetes")         -> 5 general diabetes chunks
  search("Hypertension")            -> 5 general hypertension chunks
  search("CKD Stage 3")             -> 5 general CKD chunks
  search("Metformin Lisinopril")    -> 5 drug interaction chunks

  Total: 20 chunks injected into the prompt, most irrelevant to her
  specific situation. The LLM must sift through all 20 to find the
  3-4 that actually matter.

Agent-tool RAG for Maria Garcia:

  Turn 1: Agent sees eGFR=45, metformin 1000mg, HbA1c=7.2
  Turn 1: search("metformin renal dosing eGFR 30-45")  -> 5 targeted chunks
  Turn 2: Agent sees BP=145, lisinopril 20mg, CKD stage 3
  Turn 2: search("blood pressure target CKD diabetic nephropathy") -> 5 chunks
  Turn 3: Agent generates briefing citing [1], [2], [3] from the 10 chunks

  Total: 10 chunks, all highly relevant to her specific clinical picture.
  The agent chose what to search based on what it saw in the data.
```

### The Connection to Other Documents

Agent-tool RAG sits at the intersection of several concepts covered in this series:

- **Doc 07 (Tool Use and Agentic Loop):** The search tool follows the exact tool use pattern -- the agent generates a JSON tool call, your code executes the search, and the result is fed back.
- **Doc 10 (Claude Agent SDK):** The SDK manages the multi-turn agentic loop. `max_turns=4` and `allowed_tools` are SDK options that control the agent's behavior.
- **Doc 04 (Embeddings):** The embedding model and task types (`RETRIEVAL_QUERY` vs `RETRIEVAL_DOCUMENT`) are the foundation of the search pipeline.

---

## 6. The Full Agent-Tool Flow

Now let us trace the complete flow from patient data to generated briefing. This is where all the pieces come together: the agent, the tool, the retrieval pipeline, and the structured output.

### Agent Configuration

The agent is configured in `briefing_agent.py`:

```python
# From backend/src/agents/briefing_agent.py

options = ClaudeAgentOptions(
    system_prompt=SYSTEM_PROMPT,
    model=settings.ai_model,
    mcp_servers={"briefing": briefing_tools},
    allowed_tools=["mcp__briefing__search_clinical_guidelines"],
    output_format={
        "type": "json_schema",
        "schema": PatientBriefing.model_json_schema(),
    },
    max_turns=4,
    permission_mode="bypassPermissions",
)
```

Let us break down each option:

| Option | Value | Purpose |
|--------|-------|---------|
| `system_prompt` | `SYSTEM_PROMPT` | Instructions for the agent: workflow, flag guidelines, citation rules |
| `model` | `"claude-opus-4-6"` | The LLM model to use |
| `mcp_servers` | `{"briefing": briefing_tools}` | MCP server with the search tool registered |
| `allowed_tools` | `["mcp__briefing__search_clinical_guidelines"]` | Whitelist of tools the agent can call |
| `output_format` | JSON schema from `PatientBriefing` | Structured output constraint for the final response |
| `max_turns` | `4` | Maximum conversation turns (agent + tool results) |
| `permission_mode` | `"bypassPermissions"` | Auto-approve all tool calls (server-side agent) |

### The Tool Definition

The search tool is defined in `agents/tools.py` using the `@tool` decorator from the Claude Agent SDK:

```python
# From backend/src/agents/tools.py

@tool(
    "search_clinical_guidelines",
    "Search clinical guidelines, drug interactions, and protocols. "
    "Returns relevant passages with source citations. Use this tool to find "
    "evidence-based recommendations for patient conditions and medications.",
    {
        "query": str,
        "specialty": str,
        "max_results": int,
    },
)
async def search_clinical_guidelines(args: dict) -> dict:
    """Search Qdrant for relevant clinical guideline chunks."""
    query_text = args.get("query", "")
    specialty = args.get("specialty")
    max_results = args.get("max_results", 5)

    results = await async_search(
        query=query_text,
        specialty=specialty if specialty else None,
        limit=max_results,
    )

    formatted = format_as_xml_sources(results)
    return {"content": [{"type": "text", "text": formatted}]}
```

The tool definition has three parts:

1. **Name and description.** The agent sees this when deciding which tool to call. A good description is critical -- it tells the model when and why to use this tool.
2. **Parameter schema.** `query`, `specialty`, and `max_results` define what arguments the agent can provide. The agent generates values for these parameters as JSON.
3. **Handler function.** The async function that actually performs the search. It calls `async_search()` (the async retrieval pipeline) and formats the results as XML.

### The MCP Server Bridge

The tool is registered on an MCP server using `create_sdk_mcp_server`:

```python
# From backend/src/agents/briefing_agent.py

briefing_tools = create_sdk_mcp_server(
    name="briefing",
    version="1.0.0",
    tools=[search_clinical_guidelines],
)
```

This creates an in-process MCP server that the Claude Agent SDK communicates with. The tool name becomes `mcp__briefing__search_clinical_guidelines` -- a namespaced identifier that avoids collisions if multiple MCP servers are registered.

For a deep dive into MCP servers and the protocol, see Doc 09 (MCP and A2A Protocols).

### Multi-Turn Execution Trace

Let us trace a concrete execution for Maria Garcia (Type 2 Diabetes, Hypertension, CKD Stage 3, eGFR=45, HbA1c=7.2, BP=145/90):

```
  MULTI-TURN AGENT EXECUTION
  ===========================

  ┌─────────────────────────────────────────────────────────────────────┐
  │  TURN 1: Agent receives patient data                               │
  │                                                                     │
  │  Prompt: Patient JSON (Maria Garcia, conditions, labs, meds)       │
  │  System: "You are a clinical decision support assistant..."         │
  │                                                                     │
  │  Agent thinks:                                                      │
  │    - HbA1c 7.2% is above target (ref: 4.0-5.6%)                   │
  │    - eGFR 45 mL/min is below normal (ref: 60-120)                 │
  │    - Patient is on Metformin 1000mg with impaired renal function   │
  │    - I need to check metformin dosing guidelines for CKD           │
  │                                                                     │
  │  Agent generates tool call:                                         │
  │    {                                                                │
  │      "name": "search_clinical_guidelines",                         │
  │      "input": {                                                     │
  │        "query": "metformin dose adjustment eGFR 30-45 CKD",       │
  │        "specialty": "endocrinology",                                │
  │        "max_results": 5                                             │
  │      }                                                              │
  │    }                                                                │
  └─────────────────────────────────────────────────────────────────────┘
           │
           │  SDK dispatches tool call to MCP server
           │  MCP server calls search_clinical_guidelines()
           │  async_search() embeds query + searches Qdrant
           │  Results formatted as XML
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  TURN 2: Agent receives search results                             │
  │                                                                     │
  │  Tool result: XML with 5 sources about metformin + CKD             │
  │                                                                     │
  │  Agent evaluates:                                                   │
  │    - Source [1] has metformin renal dosing table (score=0.84)       │
  │    - Source [2] has general metformin contraindications (score=0.76)│
  │    - I still need blood pressure targets for CKD patients          │
  │                                                                     │
  │  Agent generates another tool call:                                 │
  │    {                                                                │
  │      "name": "search_clinical_guidelines",                         │
  │      "input": {                                                     │
  │        "query": "blood pressure target CKD stage 3 diabetes",      │
  │        "specialty": "nephrology",                                   │
  │        "max_results": 5                                             │
  │      }                                                              │
  │    }                                                                │
  └─────────────────────────────────────────────────────────────────────┘
           │
           │  Second search executed
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  TURN 3: Agent receives second search results                      │
  │                                                                     │
  │  Tool result: XML with 5 sources about BP targets + CKD            │
  │                                                                     │
  │  Agent evaluates:                                                   │
  │    - Source [6] has BP target <130/80 for CKD + diabetes            │
  │    - Source [7] has ACE inhibitor guidance for renal protection     │
  │    - I now have enough evidence to generate the briefing           │
  │                                                                     │
  │  Agent generates structured output (PatientBriefing):              │
  │    {                                                                │
  │      "flags": [                                                     │
  │        { "category": "labs", "severity": "warning",                │
  │          "title": "Elevated HbA1c",                                │
  │          "description": "HbA1c 7.2% above target [2]..." },       │
  │        { "category": "medications", "severity": "critical",        │
  │          "title": "Metformin dose adjustment needed",              │
  │          "description": "eGFR 45: reduce to 500mg BID [1]..." }   │
  │      ],                                                             │
  │      "summary": { ... },                                            │
  │      "suggested_actions": [ ... ]                                   │
  │    }                                                                │
  └─────────────────────────────────────────────────────────────────────┘
```

### Understanding max_turns=4

The `max_turns=4` setting means the agent can execute up to 4 conversation turns total. Each turn consists of either:
- An agent message (thinking + tool call or final response), or
- A tool result message fed back to the agent

In practice, this allows:
- **1 turn**: Agent receives patient data, generates briefing immediately (no search). This happens if Qdrant has no relevant data or the patient has no flagged concerns.
- **2 turns**: Agent searches once, then generates briefing. Sufficient for a patient with one major condition.
- **3 turns**: Agent searches twice, then generates briefing. Typical for a patient like Maria Garcia with multiple interacting conditions.
- **4 turns**: Agent searches three times, then generates briefing. For complex patients with many conditions, medications, and interactions.

Why not more turns? Each turn adds latency (embedding call + Qdrant search + LLM API call). For a production system serving physicians who need quick briefings, 4 turns provides a good balance between thoroughness and speed.

```
AI DOCTOR EXAMPLE:
The max_turns budget of 4 means the agent can make up to 3 searches
before it must generate the final briefing on turn 4. In practice:

  Turn budget:  [1: receive data] [2: search + think] [3: search + think] [4: generate]

For Maria Garcia:
  Turn 1: Receive patient JSON, plan searches
  Turn 2: Search "metformin renal dosing CKD" -> get results
  Turn 3: Search "BP target CKD diabetes" -> get results, generate briefing

The agent used 3 of 4 turns. If it needed drug interaction data too,
it could use turn 3 for that search and turn 4 for the briefing.

For a healthy patient with all-normal labs:
  Turn 1: Receive patient JSON
  Turn 2: Maybe one confirmatory search, then generate briefing

The agent adapts its search strategy to the complexity of the patient.
```

### The Streaming Prompt Pattern

One subtle but critical implementation detail: the prompt must be sent as a streaming async iterator, not a plain string.

```python
# From backend/src/agents/briefing_agent.py

async def _as_stream(text: str) -> AsyncIterator[dict[str, Any]]:
    """Wrap a string prompt as a streaming input.

    The Claude Agent SDK closes stdin immediately for string prompts, which
    prevents MCP tool responses from being written back. Streaming mode keeps
    stdin open until the first result, enabling bidirectional communication.
    """
    yield {"type": "user", "message": {"role": "user", "content": text}}


# Usage:
async for message in query(prompt=_as_stream(patient_json), options=options):
    ...
```

Why? The Claude Agent SDK communicates with the Claude Code CLI via stdin/stdout. When you pass a plain string as the prompt, the SDK writes it to stdin and immediately closes the pipe. But MCP tool responses also need to be written to stdin. If stdin is already closed, the tool response cannot be delivered, and the tool call silently fails.

The `_as_stream()` wrapper converts the string into an async iterator that yields one message. The SDK keeps stdin open for async iterators, allowing bidirectional communication: the prompt goes in, and tool responses can be written back later.

This is a known gotcha documented in the project's `CLAUDE.md`:

```
| Wrong                                  | Right                                    |
| query(prompt="string", ...)            | query(prompt=async_iter, ...)            |
| String prompts close stdin, breaking   | Streaming keeps stdin open for MCP tool  |
| MCP tool communication                 | communication                            |
```

### Message Types in the Loop

As the agent executes, the SDK yields different message types. The `generate_briefing()` function handles each:

```python
# From backend/src/agents/briefing_agent.py (simplified)

async for message in query(prompt=_as_stream(patient_json), options=options):
    if isinstance(message, AssistantMessage):
        # Agent's response: text, thinking, tool calls
        turn += 1
        _log_assistant_message(message, turn)

    elif isinstance(message, UserMessage):
        # Tool results fed back to agent (automatic)
        logger.info("[turn %d] UserMessage (tool result)", turn)

    elif isinstance(message, SystemMessage):
        # SDK system events (initialization, etc.)
        logger.debug("SystemMessage: subtype=%s", message.subtype)

    elif isinstance(message, ResultMessage):
        # Final result with structured output
        if not message.is_error and message.structured_output is not None:
            briefing = PatientBriefing.model_validate(message.structured_output)
            result = BriefingResponse(**briefing.model_dump(), ...)
```

The key insight: **the SDK handles the loop automatically**. You do not need to manually extract tool calls, execute them, and send results back. The SDK dispatches tool calls to the registered MCP server, collects results, and feeds them back to the agent. Your code just listens to the message stream and extracts the final result.

For a deep dive into how the SDK manages this loop, see Doc 10 (Claude Agent SDK).

---

## 7. Formatting Results for the Agent

The final piece of the pipeline is how search results are formatted for the agent's consumption. This is not just a cosmetic choice -- the format directly affects how well the agent can parse, cite, and reason about the retrieved information.

### Why XML?

The AI Doctor formats search results as XML. This is a deliberate choice based on how LLMs process structured text:

1. **Clear boundaries.** XML tags provide unambiguous start and end markers for each piece of data. The agent can easily identify where one source ends and another begins. JSON also provides boundaries, but XML's closing tags make it visually clear even for humans reading the logs.

2. **Nested structure.** XML naturally represents the hierarchy of information: a `<clinical_guidelines>` container holds multiple `<source>` elements, each with attributes and text content. This maps well to the structure of retrieval results.

3. **LLMs parse XML well.** Language models have seen extensive XML in their training data (HTML, RSS feeds, SOAP APIs, configuration files). They can extract information from XML tags reliably. Anthropic's own documentation recommends XML for structuring information within prompts.

4. **Attribute-value pairs.** XML attributes (`id="1"`, `score="0.82"`) provide metadata inline without consuming content space. The agent can reference sources by their `id` attribute without needing to parse a separate metadata section.

### The XML Template

```python
# From backend/src/services/rag_service.py

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

A concrete example of the output:

```xml
<clinical_guidelines>
  <source id="1" document="KDIGO CKD Guidelines" section="CKD > Drug Dosing > Metformin" score="0.84">
    [CKD > Drug Dosing > Metformin] For patients with eGFR 30-45 mL/min/1.73m2,
    reduce metformin dose to a maximum of 500mg twice daily. Monitor renal function
    every 3 months. Discontinue if eGFR falls below 30 mL/min.
  </source>
  <source id="2" document="ADA Standards of Care" section="Pharmacologic Therapy > Metformin" score="0.76">
    [Pharmacologic Therapy > Metformin] Metformin is the preferred initial
    pharmacologic agent for type 2 diabetes. Assess renal function before
    initiation and periodically thereafter. Dose adjustment required when
    eGFR is 30-45 mL/min.
  </source>
  <source id="3" document="KDIGO CKD Guidelines" section="CKD > Monitoring" score="0.68">
    [CKD > Monitoring] For CKD stage 3 (eGFR 30-59), monitor serum creatinine
    and eGFR at least every 6 months. More frequent monitoring (every 3 months)
    when prescribing nephrotoxic agents or adjusting doses.
  </source>
</clinical_guidelines>
```

### How the Agent Uses the XML

The system prompt instructs the agent how to use these results:

```
CITATION RULES:
- Every clinical claim MUST reference a source_id from search results.
- If no relevant guidelines were found, state this explicitly.
- Do NOT make clinical claims without source backing.
- Format citations as [1], [2], etc. in description text.
```

When the agent generates a flag, it cites the relevant source:

```json
{
  "category": "medications",
  "severity": "critical",
  "title": "Metformin dose reduction needed",
  "description": "Patient's eGFR of 45 mL/min requires metformin dose reduction to maximum 500mg twice daily [1]. Current dose of 1000mg twice daily exceeds recommended maximum for CKD stage 3 [2].",
  "source": "ai",
  "suggested_action": "Reduce metformin to 500mg twice daily and monitor renal function every 3 months [1]"
}
```

The citations `[1]` and `[2]` map directly to the `id` attributes in the XML. The physician reading this briefing can trace each claim back to a specific guideline document and section.

### The Empty Results Case

When the search returns no results, the XML clearly communicates this:

```xml
<clinical_guidelines>No relevant guidelines found.</clinical_guidelines>
```

The system prompt handles this case:

```
CONSTRAINTS:
- If the search returns no relevant guidelines, generate the briefing
  based on the patient data and note that guidelines were unavailable.
```

This prevents the agent from hallucinating citations when no sources were found. Instead, it falls back to its general medical knowledge and explicitly notes the lack of guideline support.

```
AI DOCTOR EXAMPLE:
The XML format enables precise citation chains:

  1. Agent searches "metformin renal dosing CKD"
  2. Qdrant returns 5 chunks, formatted as XML with ids 1-5
  3. Agent reads source id="1" (KDIGO metformin renal dosing)
  4. Agent generates flag: "Reduce metformin to 500mg BID [1]"
  5. Physician reads the flag, sees [1], checks the source
  6. Source [1] traces to KDIGO CKD Guidelines, section "Drug Dosing > Metformin"

This is a complete audit trail: from patient data to search query to
retrieved guideline to clinical recommendation to citation. The physician
can verify every step.

Compare this to preprocessing RAG where all guidelines are dumped into
the prompt: the agent might cite "based on clinical guidelines" without
specifying which guideline, which section, or which version. The XML
format with source IDs makes vague citations impossible.
```

### Putting It All Together

Here is the complete data flow from raw markdown document to cited clinical recommendation:

```
  COMPLETE RAG DATA FLOW
  =======================

  INGEST (offline)                          RETRIEVE (online)
  ──────────────                            ─────────────────

  ┌──────────────┐                          ┌──────────────┐
  │ guidelines/  │                          │ Patient JSON │
  │ diabetes.md  │                          │ (Maria G.)   │
  └──────┬───────┘                          └──────┬───────┘
         │                                         │
         ▼                                         ▼
  ┌──────────────┐                          ┌──────────────┐
  │ parse_       │                          │ Agent Turn 1 │
  │ markdown()   │                          │ "I need to   │
  │              │                          │  search for  │
  │ -> Sections  │                          │  metformin   │
  │  with paths  │                          │  renal dose" │
  └──────┬───────┘                          └──────┬───────┘
         │                                         │
         ▼                                         ▼
  ┌──────────────┐                          ┌──────────────┐
  │ chunk_       │                          │ @tool search │
  │ sections()   │                          │ _clinical_   │
  │              │                          │ guidelines() │
  │ -> Document  │                          └──────┬───────┘
  │    Chunks    │                                 │
  │  (800 tok)   │                                 ▼
  └──────┬───────┘                          ┌──────────────┐
         │                                  │ embed_text() │
         ▼                                  │ RETRIEVAL_   │
  ┌──────────────┐                          │ QUERY        │
  │ embed_batch()│                          └──────┬───────┘
  │ RETRIEVAL_   │                                 │
  │ DOCUMENT     │                                 ▼
  └──────┬───────┘                          ┌──────────────┐
         │                                  │ Qdrant       │
         ▼                                  │ query_points │
  ┌──────────────┐                          │ cosine sim   │
  │ upsert_      │───────────────────────►  │ threshold≥.5 │
  │ chunks()     │     Stored vectors       │ limit=5      │
  │              │     are searched at      └──────┬───────┘
  │ -> Qdrant    │     query time                  │
  └──────────────┘                                 ▼
                                            ┌──────────────┐
                                            │ format_as_   │
                                            │ xml_sources()│
                                            │              │
                                            │ -> XML with  │
                                            │   source IDs │
                                            └──────┬───────┘
                                                   │
                                                   ▼
                                            ┌──────────────┐
                                            │ Agent Turn 2 │
                                            │              │
                                            │ Reads XML,   │
                                            │ cites [1],   │
                                            │ generates    │
                                            │ briefing     │
                                            └──────┬───────┘
                                                   │
                                                   ▼
                                            ┌──────────────┐
                                            │ PatientBrief │
                                            │ (structured) │
                                            │              │
                                            │ flags with   │
                                            │ citations    │
                                            │ [1], [2]     │
                                            └──────────────┘
```

### Key Files Summary

| File | Role | Phase |
|------|------|-------|
| `backend/src/services/document_processor.py` | Parse markdown, chunk with section paths | Ingest |
| `backend/src/models/rag.py` | `DocumentChunk` and `RetrievalResult` models | Both |
| `backend/src/services/rag_service.py` | Embed, store, search, format XML | Both |
| `backend/src/agents/tools.py` | `@tool search_clinical_guidelines` definition | Retrieve |
| `backend/src/agents/briefing_agent.py` | Agent configuration, multi-turn loop | Retrieve |
| `backend/src/services/briefing_service.py` | Routes to RAG agent or V1 fallback | Retrieve |
| `backend/src/config.py` | Qdrant URL, embedding model, dimensions | Both |

---

## Next Steps

> **Next:** Proceed to [06-RAG-EVALUATION-AND-PRODUCTION.md](./06-RAG-EVALUATION-AND-PRODUCTION.md) to learn how to evaluate RAG system quality, test retrieval pipelines, handle common failure modes, and prepare RAG systems for production deployment.

---

*Part 5 of 11: Agent Architecture & AI Model Internals Series*
*AI Doctor Assistant Project*
