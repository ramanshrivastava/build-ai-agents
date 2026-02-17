# Build AI Agents - Project Instructions

## Tech Stack

- **Backend:** FastAPI + Python 3.12
- **Frontend:** React 19 + TypeScript + Vite
- **AI:** Claude Agent SDK (not raw Anthropic API)
- **Database:** PostgreSQL 16 (Docker Compose)
- **Package Manager:** uv (not pip)

## Architecture Rules (V1)

- AI features use Claude Agent SDK with structured output (`output_format`)
- No agent tools in V1 — agent receives full patient record, reasons directly
- No SSE streaming — sync POST endpoint with spinner
- All flags `source: "ai"` (no rule-based flags yet)
- Never log patient data to console

## Common Mistakes to Avoid

| Wrong | Right |
|-------|-------|
| `from anthropic import ...` | `from claude_agent_sdk import ...` |
| `Model.parse_obj(data)` | `Model.model_validate(data)` |
| Call real LLM in tests | Mock agent responses |
| Hardcode API keys | Use environment variables |
| Skip type hints | Type hints on all functions |
| Class components in React | Functional + hooks only |
| Use pip | Use uv |
| Build agent tools (V2) | V1: no tools, no `@tool` decorator |
| SSE streaming (V2) | V1: sync POST, frontend spinner |
| Langfuse observability (V2) | V1: no observability |

## Testing Conventions

- **Backend:** pytest + pytest-asyncio
- **Frontend:** Vitest + React Testing Library
- Run `uv run pytest` before committing backend changes
- Run `npm test` before committing frontend changes
- Mock all external APIs (LLM) in tests

## Code Style

- **Python:** ruff for formatting and linting
- **TypeScript:** ESLint + Prettier
- Meaningful variable names
- Small, focused functions
- Early returns over nested conditionals

## Git Workflow

- Main branch: `main`
- Feature branches: `feature/<name>`
- Frontend work: done in `frontend` worktree branch
- Backend work: done in `backend` worktree branch
- Merge to main when features complete

## Monorepo Structure

```
build-ai-agents/
├── backend/                # FastAPI + Python 3.12
│   ├── src/
│   ├── tests/
│   ├── pyproject.toml
│   └── CLAUDE.md
├── frontend/               # React 19 + TypeScript + Vite
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── CLAUDE.md
├── docs/                   # Documentation (SCOPE-V1.md is the current plan)
├── docker-compose.yml      # PostgreSQL 16
├── .claude/                # Claude Code skills & settings
└── CLAUDE.md               # This file
```

## Worktrees (for parallel development)

```
~/projects/
├── build-ai-agents/               # main branch (full monorepo)
├── build-ai-agents-fe/            # fe branch (FE worktree)
└── build-ai-agents-be/            # be branch (BE worktree)
```

## Working in Worktrees

**Always start Claude Code from worktree root** (not inside subfolders).

### Key Documentation

Read these before starting work:
- `docs/SCOPE-V1.md` — Current iteration plan and task breakdown
- `docs/ARCHITECTURE.md` — Full system architecture vision (includes V2+ features)

### Running Commands

From repo root, use `cd` into the relevant folder:
- Frontend: `cd frontend && npm run dev`
- Backend: `cd backend && uv run uvicorn src.main:app --reload`
- Tests: `cd frontend && npm test` or `cd backend && uv run pytest`

---

## Behavioral Guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

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
