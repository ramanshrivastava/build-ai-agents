# Backend-Specific Instructions

## Monorepo Context

This is part of a monorepo. Before starting work, read:
- `../docs/ARCHITECTURE.md` — System architecture and data flow
- `../CLAUDE.md` — Project-wide instructions and patterns

Start Claude Code from repo root to ensure visibility into all docs.

## Project Structure

```
src/
├── __init__.py
├── main.py              # FastAPI app, CORS, lifespan, routers
├── config.py            # pydantic-settings config (+ Qdrant, GCP settings)
├── database.py          # SQLAlchemy async setup
├── agents/
│   ├── __init__.py
│   ├── briefing_agent.py    # RAG-augmented agent (MCP server, max_turns=4)
│   └── tools.py             # @tool search_clinical_guidelines
├── models/
│   ├── __init__.py
│   ├── orm.py           # SQLAlchemy Patient model
│   ├── rag.py           # DocumentChunk, RetrievalResult
│   └── schemas.py       # Pydantic request/response/error models
├── routers/
│   ├── __init__.py
│   ├── patients.py      # Patient endpoints
│   └── briefings.py     # Briefing endpoint
└── services/
    ├── __init__.py
    ├── patient_service.py       # Patient CRUD
    ├── briefing_service.py      # Routes to RAG agent or V1 fallback
    ├── rag_service.py           # Embed + search Qdrant
    └── document_processor.py    # Markdown parsing + chunking
```

> **RAG Architecture:** `briefing_service.py` checks Qdrant availability. If up, delegates to `agents/briefing_agent.py` (multi-turn, `max_turns=4`, with `search_clinical_guidelines` tool). If Qdrant is down, falls back to V1 single-turn agent (no tools, `max_turns=2`).

## Running the Server

```bash
cd backend && uv run uvicorn src.main:app --reload
```

## Running Tests

```bash
cd backend && uv run pytest
```

## Adding Dependencies

```bash
cd backend && uv add <package>
cd backend && uv add --dev <dev-package>
```

## Formatting & Linting

```bash
cd backend && uv run ruff format .
cd backend && uv run ruff check . --fix
```

## Key Files to Know

- `src/services/briefing_service.py` - Agent orchestration (query() + structured output)
- `src/models/schemas.py` - All Pydantic models (PatientBriefing, Flag, etc.)
- `src/config.py` - Settings via pydantic-settings

## Important Reminders

- Always use async/await for I/O operations
- Validate all LLM output against Pydantic models
- V1: all flags have `source: "ai"` (no rule-based flags)
- Use `from __future__ import annotations` for forward refs
- Use Pydantic v2 patterns (`model_validate`, not `parse_obj`)
- Import from `claude_agent_sdk`, never from `anthropic` directly
- No Langfuse observability in V1

## Claude Agent SDK Gotchas

### String prompts break MCP tool communication

When using `create_sdk_mcp_server()` with tools, you **must** pass a streaming prompt (async iterator) to `query()`, not a plain string. The SDK closes stdin immediately for string prompts, which prevents MCP tool responses from being written back. Streaming mode keeps stdin open for bidirectional communication.

```python
# WRONG — tools will silently fail
async for msg in query(prompt="patient data...", options=options):
    ...

# RIGHT — wrap as async iterator to keep stdin open
async def _as_stream(text: str) -> AsyncIterator[dict[str, Any]]:
    yield {"type": "user", "message": {"role": "user", "content": text}}

async for msg in query(prompt=_as_stream(patient_json), options=options):
    ...
```

See `src/agents/briefing_agent.py:201-208` for the production implementation.

### CLIConnectionError in ExceptionGroup during shutdown

The SDK's internal task group can wrap `CLIConnectionError` in a `BaseExceptionGroup` during `query.close()` — a race between transport shutdown and in-flight control request handlers. If you already have a valid `ResultMessage`, this error is safe to ignore. Otherwise, re-raise it.

```python
except BaseExceptionGroup as eg:
    cli_errors = eg.subgroup(CLIConnectionError)
    if cli_errors and result is not None:
        logger.warning("CLIConnectionError after result (ignoring): %s", cli_errors.exceptions[0])
    elif cli_errors:
        raise BriefingGenerationError(code="CLI_CONNECTION_ERROR", message=str(cli_errors.exceptions[0]))
    else:
        raise
```

See `src/agents/briefing_agent.py:289-305` for the production implementation.

## Environment Variables

Required in `.env` (see `.env.example`):
```
# Optional locally (SDK proxies through Claude Code CLI).
# Required for production/deployed use.
ANTHROPIC_API_KEY=
AI_MODEL=claude-opus-4-6
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/build_ai_agents
DEBUG=false
```

---

## Behavioral Guidelines

Behavioral guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
