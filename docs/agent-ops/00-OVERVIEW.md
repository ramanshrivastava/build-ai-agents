# Module 8: Agent Operations

> Production-grade observability, security, cost, and reliability for agentic systems.

---

## What this module is

Modules 1–7 teach you how to build agents. This module is what you do *after* — and during, and as you scale. The patterns here apply to every module that came before. Return to your earlier projects with these lenses; you will find things to fix.

The industry term for this is **AgentOps**, sitting alongside DevOps and MLOps as the operational discipline for shipped LLM systems. Most teams skip it. That is why most production agents are slow, expensive, jailbreakable, and inscrutable when they fail.

## Why a dedicated module

Other curricula gesture at this material in scattered places — "set up LangSmith" here, "add a guardrail" there. That framing leaves it as an afterthought. In practice, the boring middle (observability, cost, security, evals, reliability) is the highest-leverage work after a system ships and the lowest-status work in most teams. Pulling it into one explicit module is a deliberate signal: this is where production agents live or die.

## Lessons

| # | Lesson | Status |
|---|--------|--------|
| 8.1 | Tracing & Observability | *In progress* |
| 8.2 | Cost Engineering | *In progress* |
| 8.3 | Production Evals & Failure Forensics | *In progress* |
| 8.4 | Prompt Injection & Agent Security | *In progress* |
| 8.5 | Operational Patterns | *In progress* |

### 8.1 Tracing & Observability

Span design for agentic loops — tool calls, retries, sub-agent spawns, tool result truncation, model fallbacks. Tagging strategies that make spans queryable a month later (user cohort, prompt version, tool surface, model). Choosing between Langfuse, Helicone, Phoenix/Arize, and custom OpenTelemetry. Cost-per-trace dashboards. The difference between "we have logging" and "we can answer 'why did this run cost $4'."

### 8.2 Cost Engineering

Token accounting at scale. Prompt-caching ROI math: when caching pays off, when it doesn't, when it actively hurts (cache misses on long stable contexts can be more expensive than no cache). Batch API economics. Streaming vs non-streaming cost trade-offs. Why the headline price-per-million-tokens is rarely your effective cost. Patterns from real production systems including which optimizations move the needle and which don't.

### 8.3 Production Evals & Failure Forensics

Note this is **production** evals — not eval methodology in general (which lives in Module 2 for RAG and Module 3 for tool calling). Production evals are the regression suite, the replay harness, the eval-on-real-traffic pipeline. Topics: snapshot testing for non-deterministic outputs, deterministic replay of agent runs, regression detection in CI, real-traffic shadow eval, why temperature=0 is not enough. Forensics: reading a failed trace, root-causing hallucinations, the "did the model fail or did the tool fail" decomposition.

### 8.4 Prompt Injection & Agent Security

Direct prompt injection (the user is the attacker) vs indirect injection (a tool result, a retrieved document, a webpage is the attacker). Tool-permission scoping — every tool an agent can call is part of the attack surface. Untrusted-content handling patterns. Real attacks documented in the public record: the Bing Chat early-2023 jailbreaks, ChatGPT plugin exfiltration, MCP server supply-chain risks. Why "system prompt says 'ignore later instructions'" is not a defense.

### 8.5 Operational Patterns

Circuit breakers when the model provider is degraded. Graceful degradation: model fallback chains, response truncation, partial-failure UX. Rate limiting and per-user fairness. Streaming UX and latency budgets — TTFB, perceived latency, partial rendering, the difference between "fast" and "feels fast." The boring stuff that keeps shipped agents alive on bad days.

## Specialist tracks (out of scope here)

These exist in adjacent industry curricula but are deliberately *not* in this module's core path. They get specialist-track treatment:

- **Fine-tuning and RLVR** — narrow tools for narrow problems. For most app developers in 2026, prompt + retrieval + tool design beats fine-tuning. Treat as "here's when this is the right tool," not as a default path.
- **Multi-modal RAG** — useful in narrow niches (PDFs with figures, video QA). For most apps, OCR-then-text-RAG outperforms direct image embedding.
- **Self-hosted OSS LLMs** — justified by compliance, cost-at-scale, or research. For 90% of teams, calling Anthropic / OpenAI / Vertex is cheaper, faster, and higher quality.

If the specialist track is right for your problem, follow other resources for it. This module focuses on what every production agent needs.

## Status

This is the module overview. Lesson prose (8.1–8.5) is in progress and ships in follow-up PRs. Each lesson will follow the existing module style: long-form markdown, runnable code where applicable, citations to primary sources for any quantified claim, and `> [!WARNING]` callouts marked `**Reality check —**` for places where the industry consensus is wrong or oversold.
