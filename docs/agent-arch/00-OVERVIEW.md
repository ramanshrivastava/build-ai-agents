# Agent Architecture & AI Model Internals

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

This is an educational series about LLM APIs, agent patterns, protocols, and transformer internals.

These documents are written for developers who:

- Build with LLM APIs (Anthropic, OpenAI, etc.) and want to understand what happens under the hood
- Are curious about how transformers actually work -- from tokens to attention to generation
- Need to understand agent patterns, tool use, and protocols (MCP, A2A) for production systems
- Want to validate their understanding of AI/ML engineering concepts

**This is not a quickstart.** It prioritizes depth over speed. Each document explains *why* before *how*, building mental models that transfer across providers and frameworks.

---

## Prerequisites

Before reading this series, you should have:

- **Basic Python/JavaScript**: Can read code, write functions, make HTTP requests with `requests` or `fetch`
- **HTTP/REST Concepts**: Understand headers, JSON, request/response cycle, status codes
- **Terminal Comfort**: Can run `curl` commands, pipe output to `jq`, read JSON output
- **Environment Variables**: Know how to set and read variables like `ANTHROPIC_API_KEY`

You do **not** need:

- Machine learning or math background -- the transformer section builds from first principles
- Prior experience with any LLM API -- Document 01 starts from zero
- Understanding of neural networks -- we build up from tokens and vectors
- Statistics beyond "what is an average" -- we explain probability distributions where needed

---

## Recommended Reading Order

| Document | Title | Description |
|----------|-------|-------------|
| **00-OVERVIEW.md** | This overview | Series structure, prerequisites, conventions |
| **01-ANTHROPIC-API-FUNDAMENTALS.md** | Anthropic API Fundamentals | Making API calls, authentication, messages, models, parameters |
| **02-TOOL-USE-AND-AGENTIC-LOOP.md** | Tool Use & The Agentic Loop | Tool definitions, JSON Schema, the two-step dance, multi-tool, frameworks |
| **03-PROMPT-CACHING-AND-OPTIMIZATION.md** | Prompt Caching & Optimization | KV cache internals, API prompt caching, cost and latency strategies |
| **04-MCP-AND-A2A-PROTOCOLS.md** | MCP & A2A Protocols | Model Context Protocol, Agent2Agent, tool/agent communication standards |
| **05-TRANSFORMER-ARCHITECTURE.md** | Transformer Architecture | Tokenization, embeddings, attention mechanism, generation -- full visual treatment |
| **06-TRAINING-AND-RUNNING-MODELS.md** | Training & Running Models | Pre-training, RLHF, Constitutional AI, Ollama, quantization, local inference |

---

## Suggested Paths

### Builders Path (API to Production)

**Goal**: Ship applications that use LLM APIs effectively.

```
00 → 01 → 02 → 03 → 04
│    │    │    │    │
│    │    │    │    └─ MCP/A2A: Connect agents to tools and other agents
│    │    │    └─ Caching: Cut costs 90% with prompt caching
│    │    └─ Tool use: Let Claude call functions and APIs
│    └─ API basics: Authentication, messages, models, parameters
└─ This overview
```

**Time estimate**: 4-6 hours of focused reading. Run the `scripts/` examples as you go.

### Understanding AI Path (How It Works)

**Goal**: Understand what happens inside a language model, from text input to generated output.

```
00 → 05 → 06
│    │    │
│    │    └─ Training: Pre-training, RLHF, quantization, running locally
│    └─ Transformers: Tokens, embeddings, attention, generation
└─ This overview
```

**Time estimate**: 3-4 hours. The transformer document is dense -- give it time.

### Knowledge Check Path

**Goal**: Validate AI/ML engineering knowledge with both practical API skills and theoretical depth.

```
01 → 02 → 05 → 06
│    │    │    │
│    │    │    └─ Training pipeline: Pre-training → RLHF → deployment
│    │    └─ Architecture: "Explain the transformer" (the most fundamental question)
│    └─ Tool use: Agentic patterns (core to modern AI system design)
└─ API fundamentals: Show you can actually build with these systems
```

**Time estimate**: 5-7 hours. Focus on the "why" behind each concept.

### Full Sequential Path

Read 00 through 06 in order. Each document builds on the previous. This is the most thorough approach but takes 8-12 hours.

---

## Conventions Used

### Formatting

**Code Blocks**: Shell commands, JSON payloads, and Python code appear in fenced code blocks with language hints:

```bash
# Example: Making an API call
curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -d '{"model": "claude-sonnet-4-5-20250929", "max_tokens": 1024, ...}'
```

```json
{
  "role": "assistant",
  "content": [{"type": "text", "text": "Hello!"}]
}
```

**Inline Code**: Commands, file paths, API fields, and technical terms appear in `backticks` (e.g., `max_tokens`, `scripts/test-tool-call.sh`, `stop_reason`).

**Tables**: Used for model comparisons, parameter references, and structured lists.

**ASCII Diagrams**: Architecture flows, data structures, and protocol sequences use text-based diagrams.

**Mermaid Diagrams**: Flowcharts and sequence diagrams use fenced `mermaid` code blocks. See [`docs/tooling/MERMAID-CHEATSHEET.md`](../tooling/MERMAID-CHEATSHEET.md) for syntax reference.

### AI Doctor Callouts

Examples specific to the AI Doctor Assistant app use this format:

```
AI DOCTOR EXAMPLE:
The backend sends the full patient record (vitals, medications, labs)
in the messages array to Claude. Every API call includes the complete
context because the API is stateless — there is no session.
```

These ground abstract concepts in the actual application.

### Emphasis Patterns

- **Bold**: Key terms on first mention, important warnings, critical concepts
- *Italics*: Emphasis within explanations, contrasts, nuance
- ALL CAPS: Reserved for acronyms (LLM, MCP, SSE) and environment variables (ANTHROPIC_API_KEY)

---

## How to Use This Series

### For Learning

1. **Read 01** with a terminal open. Run the `scripts/test-tool-call.sh` script to see a real API response.
2. **Read 02** and run `scripts/test-tool-call-opus-step2.sh` to see the full tool-use round trip.
3. **Read 03** to understand why caching changes the economics of LLM applications.
4. **Read 04** when you need to connect agents to external tools or other agents.
5. **Read 05-06** when you want to understand what happens *inside* the model. These are independent of the API docs.

### For Building with LLM APIs

1. Start with **01** for authentication, models, and parameters.
2. Read **02** to implement tool use (required for most production applications).
3. Read **03** before going to production -- caching can cut your API bill by 90%.
4. Read **04** if building multi-agent systems or integrating with MCP-compatible tools.

### For Knowledge Validation

1. Read **01** and be able to explain: stateless API, messages array, token counting, model selection tradeoffs.
2. Read **02** and be able to whiteboard the agentic loop (tool_use → execute → tool_result → response).
3. Read **05** and be able to explain: tokenization, embeddings, self-attention, why transformers are parallelizable.
4. Read **06** and be able to explain: pre-training vs fine-tuning vs RLHF, quantization tradeoffs, why RLHF matters.

### For Reference

- **01**: API authentication, model IDs, parameter reference, response structure
- **02**: Tool definition schema, agentic loop flow, framework comparison
- **03**: Caching rules, cost calculation formulas, optimization checklist
- **04**: MCP protocol specification, A2A protocol, tool vs agent distinction
- **05**: Transformer component reference, attention mechanism walkthrough
- **06**: Training pipeline stages, quantization types, Ollama commands

---

## What This Series Does NOT Cover

- **Fine-tuning your own models**: We cover the concept (what RLHF is, how fine-tuning works) but not the practice (no PyTorch training loops)
- **Specific ML frameworks**: PyTorch, JAX, TensorFlow are mentioned for context but not taught. Concepts are framework-agnostic.
- **Production MLOps**: Model serving at scale, A/B testing models, model registries, feature stores. See MLOps-specific resources.
- **Computer vision or non-text modalities in depth**: We mention multimodal inputs (images in the messages API) but focus on text.
- **OpenAI/Google/other provider APIs in detail**: Concepts transfer, but code examples use Anthropic's API. Provider differences are noted where significant.
- **Building a vector database or RAG system**: Mentioned in context of embeddings and tool use, but not a dedicated tutorial.

---

## Cross-References

This series connects to the **Infrastructure Architecture Series** (`docs/infra-arch/`) in several places:

- **`infra-arch/07-GPU-AND-AGENTS.md`**: GPU node scheduling for local model inference, agent workload isolation in Kubernetes. Read after `06-TRAINING-AND-RUNNING-MODELS.md` if you plan to run models on your own infrastructure.
- **`infra-arch/05-APP-ON-K8S.md`**: How the AI Doctor backend (which calls the Claude API) is deployed as a Kubernetes Pod. The API patterns from `01-ANTHROPIC-API-FUNDAMENTALS.md` are what the backend executes inside that Pod.
- **`infra-arch/06-DEPLOYMENT-PIPELINE.md`**: CI/CD pipeline that builds and deploys the backend container, including how API keys are injected as Kubernetes Secrets.

---

## Document Maintenance

These documents reflect:

- **Anthropic API**: `anthropic-version: 2023-06-01` (stable version header as of 2025)
- **Models**: Claude Opus 4, Claude Sonnet 4.5, Claude Haiku 4.5 (model IDs current as of 2025)
- **MCP Protocol**: Model Context Protocol specification (2024-2025)
- **AI Doctor**: V1 complete (FastAPI + React 19 + PostgreSQL), V2 in planning

As Anthropic releases new API versions or models, documents 01-03 may need updates. The transformer architecture (05) and training concepts (06) are stable across model generations.

---

**Next Steps**: Proceed to `01-ANTHROPIC-API-FUNDAMENTALS.md` to learn how the Anthropic Messages API works, or jump to `05-TRANSFORMER-ARCHITECTURE.md` if you want to start with how models work internally.
