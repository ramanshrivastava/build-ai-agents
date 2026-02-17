# AI Doctor Assistant - POC Plan (Iteration 3)

> Created: February 4, 2026
> Status: Draft for approval

## Focus: AI-Enabled Development Environment (Phase 0)

> **"Set up for AI-first development before writing any code"**
> Building the foundation for parallel, skill-guided development.

---

## What This Iteration Delivers

Before writing any application code, we establish an AI-optimized development workflow:

| Feature | Description |
|---------|-------------|
| **Git Worktrees** | Parallel FE/BE development in isolated directories |
| **Custom Skills** | 5 project-specific SKILL.md files for Claude Code |
| **CLAUDE.md** | Root + worktree-specific instructions |
| **uv** | Modern Python package manager (not pip) |
| **Hooks** | Auto-formatting on file changes |
| **Permissions** | Pre-allowed commands to reduce prompts |

---

## Why Phase 0 First?

This is **Boris Cherny's approach** (Claude Code creator):

1. **Parallel sessions** - Run 5 Claudes simultaneously on different tasks
2. **No conflicts** - Git worktrees provide isolated working directories
3. **Consistent patterns** - Skills encode best practices
4. **Team learning** - CLAUDE.md captures mistakes and decisions
5. **Faster iteration** - Pre-allowed commands eliminate prompt fatigue

---

## Architecture Decision: Rules in Code → Agent

Before setting up the environment, we locked in this architecture pattern:

```
┌─────────────────────────────────────────────────────────────┐
│                     Two-Step Briefing Flow                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  STEP 1: Deterministic Rules (Python)                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  FlagAnalyzer.apply_rules(patient)                     │  │
│  │  • Overdue labs check (date math)                      │  │
│  │  • Drug interaction check (lookup table)               │  │
│  │  • Missing vaccine check (age-based rules)             │  │
│  │  → Returns: List[Flag] (100% deterministic)            │  │
│  └───────────────────────────────────────────────────────┘  │
│                             │                                │
│                             ▼                                │
│  STEP 2: AI Synthesis (Claude Agent SDK)                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  BriefingAgent.generate(patient, rule_flags)           │  │
│  │  • Receives: full patient record + rule-based flags    │  │
│  │  • Generates: clinical summary, AI insights            │  │
│  │  • Adds: AI-detected patterns rules might miss         │  │
│  │  • Returns: PatientBriefing (Pydantic validated)       │  │
│  │  • Hooks: Langfuse tracing, audit logging              │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Why This Pattern?

| Benefit | Explanation |
|---------|-------------|
| **Auditability** | Can prove which flags came from rules vs AI (compliance) |
| **Testability** | Unit test rules separately, mock agent for integration tests |
| **Reliability** | Rules are 100% deterministic (critical for healthcare) |
| **Traceability** | Clear separation: `source: "rule"` vs `source: "ai"` |

---

## Claude Agent SDK Architecture (Correct Implementation)

> **Important:** The `.claude/skills/` folder is for **Claude Code** (the development CLI), NOT for the agent we're building. The BriefingAgent uses **custom tools** via the `@tool` decorator.

### Agent Tools (for BriefingAgent)

```python
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    tool,
    create_sdk_mcp_server,
    HookMatcher
)

# STEP 1: Define custom tools (deterministic operations)
@tool("apply_flag_rules", "Apply rule-based flag detection", {"patient_id": str})
async def apply_flag_rules(args: dict) -> dict:
    """100% deterministic - Python rules, not LLM."""
    patient = await patient_service.get(args["patient_id"])
    flags = flag_analyzer.apply_rules(patient)
    return {
        "content": [{
            "type": "text",
            "text": json.dumps([f.model_dump() for f in flags])
        }]
    }

@tool("fetch_patient", "Fetch patient record", {"patient_id": str})
async def fetch_patient(args: dict) -> dict:
    patient = await patient_service.get(args["patient_id"])
    return {
        "content": [{
            "type": "text",
            "text": patient.model_dump_json()
        }]
    }

@tool("check_drug_interactions", "Check medication interactions", {"medications": list})
async def check_drug_interactions(args: dict) -> dict:
    interactions = drug_db.check(args["medications"])
    return {
        "content": [{
            "type": "text",
            "text": json.dumps(interactions)
        }]
    }

# STEP 2: Create MCP server with our tools
briefing_tools = create_sdk_mcp_server(
    name="briefing",
    version="1.0.0",
    tools=[apply_flag_rules, fetch_patient, check_drug_interactions]
)
```

### Structured Output Schema

```python
# STEP 3: Define structured output schema (auto-validated by SDK)
BRIEFING_SCHEMA = {
    "type": "object",
    "properties": {
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "severity": {"type": "string", "enum": ["critical", "warning", "info"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "source": {"type": "string", "enum": ["rule", "ai"]},
                    "suggested_action": {"type": "string"}
                },
                "required": ["category", "severity", "title", "source"]
            }
        },
        "summary": {
            "type": "object",
            "properties": {
                "one_liner": {"type": "string"},
                "key_conditions": {"type": "array", "items": {"type": "string"}},
                "relevant_history": {"type": "string"}
            },
            "required": ["one_liner", "key_conditions"]
        },
        "suggested_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "reason": {"type": "string"},
                    "priority": {"type": "integer"}
                },
                "required": ["action", "priority"]
            }
        }
    },
    "required": ["flags", "summary", "suggested_actions"]
}
```

### Agent Configuration with Hooks

```python
# STEP 4: Configure hooks for observability (Langfuse)
async def langfuse_trace_hook(input_data, tool_use_id, context):
    """Log every tool call to Langfuse for observability."""
    tool_name = input_data.get('tool_name', 'unknown')
    langfuse.trace(
        name=f"tool:{tool_name}",
        input=input_data.get('tool_input'),
        metadata={"tool_use_id": tool_use_id}
    )
    return {}

async def audit_log_hook(input_data, tool_use_id, context):
    """Log to audit file for HIPAA compliance."""
    with open('./audit.log', 'a') as f:
        f.write(f"{datetime.now().isoformat()}: {input_data.get('tool_name')}\n")
    return {}

# STEP 5: Full agent configuration
options = ClaudeAgentOptions(
    mcp_servers={"briefing": briefing_tools},
    allowed_tools=[
        "mcp__briefing__apply_flag_rules",
        "mcp__briefing__fetch_patient",
        "mcp__briefing__check_drug_interactions"
    ],
    output_format={"type": "json_schema", "schema": BRIEFING_SCHEMA},
    hooks={
        "PreToolUse": [HookMatcher(hooks=[langfuse_trace_hook, audit_log_hook])],
        "PostToolUse": [HookMatcher(hooks=[langfuse_trace_hook])]
    },
    system_prompt=BRIEFING_SYSTEM_PROMPT
)
```

### Generate Briefing

```python
# STEP 6: Generate briefing
async def generate_briefing(patient_id: str) -> PatientBriefing:
    async for message in query(
        prompt=f"""
        Generate a pre-consultation briefing for patient {patient_id}.

        Steps:
        1. First call apply_flag_rules to get deterministic rule-based flags
        2. Call fetch_patient to get the full patient record
        3. Call check_drug_interactions with their medications
        4. Synthesize a briefing that:
           - Includes ALL rule-based flags (don't recompute them)
           - Adds AI-detected patterns the rules might miss
           - Provides a concise clinical summary
           - Lists prioritized suggested actions

        Tag each flag with source: "rule" or "ai"
        """,
        options=options
    ):
        if hasattr(message, "structured_output"):
            return PatientBriefing.model_validate(message.structured_output)
```

---

## Git Worktrees Setup

### Directory Structure

```
~/projects/
├── ai-doctor-assistant/          # Main repo (architecture, docs, shared)
├── ai-doctor-assistant-frontend/ # Worktree for FE development
└── ai-doctor-assistant-backend/  # Worktree for BE development
```

### Why Sibling Directories?

- IDE opens each as separate project
- Clean separation for parallel Claude Code sessions
- No risk of accidentally committing worktree folders
- Each session has isolated files (no conflicts)

### Commands to Execute

```bash
cd ~/projects/ai-doctor-assistant

# Initialize git if needed
git init
git add .
git commit -m "Initial commit with docs and plan"

# Create frontend worktree
git worktree add ../ai-doctor-assistant-frontend -b frontend

# Create backend worktree
git worktree add ../ai-doctor-assistant-backend -b backend
```

### Workflow After Setup

```
Terminal 1 (Main):     cd ai-doctor-assistant && claude
Terminal 2 (Frontend): cd ai-doctor-assistant-frontend && claude
Terminal 3 (Backend):  cd ai-doctor-assistant-backend && claude
```

---

## Custom Skills for Claude Code

> **Note:** These skills are for **Claude Code** (the development CLI) to help YOU write code. They are NOT for the BriefingAgent we're building.

### Skills Overview

| # | Skill | Location | Purpose |
|---|-------|----------|---------|
| 1 | react-fe-dev | `.claude/skills/react-fe-dev/SKILL.md` | React + Vite + TypeScript patterns |
| 2 | fastapi-backend | `.claude/skills/fastapi-backend/SKILL.md` | FastAPI + Pydantic + async patterns |
| 3 | claude-agent-dev | `.claude/skills/claude-agent-dev/SKILL.md` | Agent SDK + Langfuse + tools |
| 4 | staff-architect | `.claude/skills/staff-architect/SKILL.md` | Architecture decisions |
| 5 | code-reviewer | `.claude/skills/code-reviewer/SKILL.md` | Review + refactoring safety |

### Skill 1: react-fe-dev

**File:** `.claude/skills/react-fe-dev/SKILL.md`

```yaml
---
name: react-fe-dev
description: React frontend development patterns for AI Doctor Assistant
---
```

**Content:**
- React 18+ with TypeScript strict mode
- Vite for build tooling
- Component patterns: functional + hooks only
- State: React Query for server state, Zustand for client state (if needed)
- Testing: Vitest + React Testing Library
- Styling: Tailwind CSS
- File structure: feature-based folders
- No class components
- Prefer composition over prop drilling
- Use `useMemo`/`useCallback` judiciously (not everywhere)

### Skill 2: fastapi-backend

**File:** `.claude/skills/fastapi-backend/SKILL.md`

```yaml
---
name: fastapi-backend
description: FastAPI backend patterns for AI Doctor Assistant
---
```

**Content:**
- FastAPI with async/await patterns
- Pydantic v2 for validation (use `model_validate`, not `parse_obj`)
- SQLAlchemy 2.0 with async sessions
- Dependency injection via FastAPI's `Depends`
- Testing: pytest-asyncio + httpx TestClient
- Error handling: HTTPException with proper status codes
- Use `from __future__ import annotations` for forward refs
- Type hints on all function signatures
- Routers organized by domain (patients, briefings)
- Use `uv` for dependency management (not pip)

### Skill 3: claude-agent-dev

**File:** `.claude/skills/claude-agent-dev/SKILL.md`

```yaml
---
name: claude-agent-dev
description: Claude Agent SDK patterns and best practices
---
```

**Content:**
- Use `claude_agent_sdk` package (pip install claude-agent-sdk)
- Create custom tools via `@tool` decorator + `create_sdk_mcp_server()`
- Tools naming: `mcp__<server>__<tool_name>`
- Use `output_format` with JSON schema for structured outputs
- Implement hooks for observability (PreToolUse, PostToolUse)
- Integrate Langfuse for tracing via hooks
- Use `query()` for one-off tasks
- Use `ClaudeSDKClient` for continuous conversation
- Always validate output against Pydantic models
- Mock agent responses in tests (never call real API)
- SDK supports Python 3.10, 3.11, 3.12, 3.13

### Skill 4: staff-architect

**File:** `.claude/skills/staff-architect/SKILL.md`

```yaml
---
name: staff-architect
description: Architecture guidance for AI Doctor Assistant
---
```

**Content:**
- Keep services loosely coupled
- API versioning: `/api/v1/...`
- Error handling: structured error responses with codes
- Document decisions in ADRs (Architecture Decision Records)
- Data flow: Frontend → API → Service → Agent → Tools
- Don't over-engineer for hypothetical futures
- Prefer explicit over implicit
- Healthcare context: auditability, traceability, determinism where possible

### Skill 5: code-reviewer

**File:** `.claude/skills/code-reviewer/SKILL.md`

```yaml
---
name: code-reviewer
description: Code review and refactoring guidelines
---
```

**Content:**
- Never change code without reading it first
- Run tests before and after changes
- Check for breaking API changes
- Verify error handling
- Ensure no patient data logged in production
- Look for hardcoded secrets
- Check for proper async/await usage
- Verify Pydantic model validations
- Ensure proper type hints
- Check test coverage for new code

---

## CLAUDE.md Configuration

### Root CLAUDE.md

**File:** `CLAUDE.md` (in repo root)

```markdown
# AI Doctor Assistant - Project Instructions

## Tech Stack
- Backend: FastAPI + Python 3.12
- Frontend: React 18 + TypeScript + Vite
- AI: Claude Agent SDK (not raw Anthropic API)
- Observability: Langfuse
- Database: SQLite (POC), PostgreSQL (production)
- Package Manager: uv (not pip)

## Architecture Rules
- All AI features use Claude Agent SDK with custom tools
- Rule-based logic = deterministic Python code (FlagAnalyzer)
- AI analysis = agent reasoning on top of rule results
- Two-step flow: Rules first → Agent synthesis second
- Custom tools via @tool decorator + create_sdk_mcp_server()
- Structured output via output_format with JSON schema
- Never log patient data to console

## Common Mistakes to Avoid
- Don't import from `anthropic` directly - use `claude_agent_sdk`
- Don't use Pydantic v1 patterns (`parse_obj`) - use v2 (`model_validate`)
- Don't call LLM in tests - mock responses
- Don't hardcode API keys - use environment variables
- Don't skip type hints on function signatures
- Don't create class components in React - use functional + hooks
- Don't use pip - use uv for Python dependencies

## Testing Conventions
- Backend: pytest + pytest-asyncio
- Frontend: Vitest + React Testing Library
- Run `pytest` before committing backend changes
- Run `npm test` before committing frontend changes
- Mock all external APIs (LLM, Langfuse) in tests

## Code Style
- Python: ruff for formatting and linting
- TypeScript: ESLint + Prettier
- Use meaningful variable names
- Keep functions small and focused
- Prefer early returns over nested conditionals

## Git Workflow
- Main branch: `main`
- Feature branches: `feature/<name>`
- Frontend work: done in `frontend` worktree branch
- Backend work: done in `backend` worktree branch
- Merge to main when features complete
```

### Backend-Specific CLAUDE.md

**File:** `ai-doctor-assistant-backend/CLAUDE.md`

```markdown
# Backend-Specific Instructions

## Project Structure
```
src/
├── __init__.py
├── main.py              # FastAPI app entry
├── config.py            # Settings, env vars
├── models/              # Pydantic models
├── services/            # Business logic
├── agents/              # Claude Agent SDK agents
│   ├── briefing_agent.py
│   ├── tools.py         # @tool definitions
│   └── hooks.py         # Langfuse hooks
├── routers/             # API routes
└── database.py          # SQLAlchemy setup
```

## Running the Server
```bash
uv run uvicorn src.main:app --reload
```

## Running Tests
```bash
uv run pytest
```

## Adding Dependencies
```bash
uv add <package>
uv add --dev <dev-package>
```

## Key Files to Know
- `src/agents/tools.py` - Custom tools for BriefingAgent
- `src/services/flag_analyzer.py` - Deterministic rule-based flags
- `src/models/briefing.py` - Pydantic output models

## Don't Forget
- Always use async/await for I/O operations
- Validate all LLM output against Pydantic models
- Tag flags with source: "rule" or "ai"
```

### Frontend-Specific CLAUDE.md

**File:** `ai-doctor-assistant-frontend/CLAUDE.md`

```markdown
# Frontend-Specific Instructions

## Project Structure
```
src/
├── components/
│   ├── PatientList/
│   ├── Briefing/
│   └── common/
├── pages/
├── hooks/
├── services/
│   └── api.ts
├── types/
└── App.tsx
```

## Running the Dev Server
```bash
npm run dev
```

## Running Tests
```bash
npm test
```

## Key Patterns
- Use React Query for server state (`useQuery`, `useMutation`)
- Co-locate tests with components (Component.test.tsx)
- Use Tailwind CSS for styling
- Type all props with interfaces

## API Integration
- All API calls go through `services/api.ts`
- Use the `useBriefing` hook for patient briefings
- Handle loading/error states in components
```

---

## uv Setup (Python Package Manager)

### Why uv?

| Feature | uv | pip |
|---------|-----|-----|
| Speed | 80x faster | Baseline |
| Lock file | `uv.lock` (reproducible) | `requirements.txt` (not locked) |
| Global cache | Yes (saves disk space) | No (duplicates) |
| Project init | `uv init` | Manual |

### Backend Initialization

```bash
cd ai-doctor-assistant-backend

# Initialize with Python 3.12
uv init --python 3.12

# Add production dependencies
uv add fastapi uvicorn pydantic sqlalchemy aiosqlite
uv add claude-agent-sdk langfuse

# Add dev dependencies
uv add --dev pytest pytest-asyncio pytest-mock httpx ruff

# Sync environment
uv sync
```

### Files Created

```
ai-doctor-assistant-backend/
├── .python-version          # 3.12
├── pyproject.toml           # Dependencies + metadata
├── uv.lock                  # Locked versions (commit this!)
└── .venv/                   # Virtual environment
```

### Running Commands

```bash
# Run server
uv run uvicorn src.main:app --reload

# Run tests
uv run pytest

# Run ruff
uv run ruff check .
uv run ruff format .
```

---

## Hooks Configuration

**File:** `.claude/settings.json`

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "cd backend && uv run ruff format . && uv run ruff check . --fix || true"
          }
        ]
      }
    ]
  }
}
```

**What this does:**
- After any file Write or Edit, automatically runs ruff to format Python code
- Uses `uv run` to run ruff in the correct environment
- The `|| true` ensures the hook doesn't fail the operation if ruff has issues

---

## Permissions to Pre-Allow

Run these commands to reduce permission prompts:

```bash
/permissions allow "uv *"
/permissions allow "uv run *"
/permissions allow "pytest *"
/permissions allow "npm run *"
/permissions allow "npm test"
/permissions allow "ruff *"
/permissions allow "uvicorn *"
```

---

## External Skills to Install

Install skills from [skills.sh](https://skills.sh/):

```bash
# Install Vercel's React/Next.js optimization skills
npx skills i vercel-labs/agent-skills

# Discover more as needed
npx skills find fastapi
npx skills find pytest
```

---

## Project Structure After Phase 0

```
ai-doctor-assistant/                      # Main repo
├── .claude/
│   ├── settings.json                     # Hooks configuration
│   └── skills/
│       ├── react-fe-dev/SKILL.md
│       ├── fastapi-backend/SKILL.md
│       ├── claude-agent-dev/SKILL.md
│       ├── staff-architect/SKILL.md
│       └── code-reviewer/SKILL.md
├── docs/
│   ├── RAW-PRD.md
│   ├── PLAN-ITERATION-1.md
│   ├── PLAN-ITERATION-2.md
│   └── PLAN-ITERATION-3.md               # This file
├── CLAUDE.md                              # Root project instructions
└── README.md

ai-doctor-assistant-frontend/              # Frontend worktree
├── CLAUDE.md                              # FE-specific instructions
├── src/
├── package.json
└── ...

ai-doctor-assistant-backend/               # Backend worktree
├── CLAUDE.md                              # BE-specific instructions
├── src/                                   # Source code (not app/)
│   ├── __init__.py
│   ├── main.py
│   └── ...
├── tests/
├── pyproject.toml
├── uv.lock
└── .python-version                        # 3.12
```

---

## Implementation Checklist

### Phase 0: Development Environment Setup

- [ ] **Git Setup**
  - [ ] Initialize git repo (if needed)
  - [ ] Create initial commit
  - [ ] Create frontend worktree: `git worktree add ../ai-doctor-assistant-frontend -b frontend`
  - [ ] Create backend worktree: `git worktree add ../ai-doctor-assistant-backend -b backend`

- [ ] **Backend Setup (uv)**
  - [ ] `cd ../ai-doctor-assistant-backend`
  - [ ] `uv init --python 3.12`
  - [ ] Add dependencies with `uv add`
  - [ ] Create `src/` directory structure
  - [ ] Create backend-specific CLAUDE.md

- [ ] **Frontend Setup**
  - [ ] `cd ../ai-doctor-assistant-frontend`
  - [ ] `npm create vite@latest . -- --template react-ts`
  - [ ] Create `src/` directory structure
  - [ ] Create frontend-specific CLAUDE.md

- [ ] **Skills Creation (5 skills)**
  - [ ] Create `.claude/skills/` directory
  - [ ] Create react-fe-dev/SKILL.md
  - [ ] Create fastapi-backend/SKILL.md
  - [ ] Create claude-agent-dev/SKILL.md
  - [ ] Create staff-architect/SKILL.md
  - [ ] Create code-reviewer/SKILL.md

- [ ] **Project Configuration**
  - [ ] Create root CLAUDE.md
  - [ ] Create .claude/settings.json with hooks

- [ ] **Permissions Setup**
  - [ ] Allow uv commands
  - [ ] Allow pytest commands
  - [ ] Allow npm commands
  - [ ] Allow ruff commands
  - [ ] Allow uvicorn commands

- [ ] **External Skills**
  - [ ] Install vercel-labs/agent-skills

- [ ] **Verification**
  - [ ] Can run `claude` in main directory
  - [ ] Can run `claude` in frontend worktree
  - [ ] Can run `claude` in backend worktree
  - [ ] Hooks trigger on file changes

---

## Verification Plan

### Manual Testing

1. **Git Worktrees:**
   - [ ] `cd ../ai-doctor-assistant-frontend && git status` shows frontend branch
   - [ ] `cd ../ai-doctor-assistant-backend && git status` shows backend branch
   - [ ] Changes in one worktree don't affect others

2. **uv Setup:**
   - [ ] `cd ../ai-doctor-assistant-backend && uv run python --version` shows 3.12
   - [ ] `uv.lock` exists and is committed

3. **Skills Loading:**
   - [ ] In Claude session, reference `@react-fe-dev` skill
   - [ ] Verify skill content is understood

4. **Hooks:**
   - [ ] Create a poorly-formatted Python file in backend
   - [ ] Edit it with Claude
   - [ ] Verify ruff formats it automatically

5. **CLAUDE.md:**
   - [ ] Start new Claude session in backend worktree
   - [ ] Ask about project tech stack
   - [ ] Verify it knows "Claude Agent SDK, not raw anthropic" and "uv, not pip"

---

## Success Criteria

Phase 0 is complete when:

1. **Worktrees work:** Can run parallel Claude sessions in FE/BE directories
2. **Skills created:** All 5 SKILL.md files exist with proper content
3. **CLAUDE.md active:** Root + worktree-specific files understood
4. **uv working:** Backend uses uv with Python 3.12
5. **Hooks fire:** Python files auto-format on save
6. **Permissions set:** Common commands don't prompt for approval

---

## Next Steps After Phase 0

Once environment is set up, proceed to:

1. **Phase 1:** Foundation Setup (FastAPI + React initialization)
2. **Phase 2:** Flag Analyzer (Rule-based detection as custom tool)
3. **Phase 3:** Claude Agent SDK Integration (BriefingAgent with tools)
4. **Phase 4:** Structured Output + Hooks (Langfuse observability)
5. **Phase 5-6:** Frontend components
6. **Phase 7:** Integration & Polish

See [PLAN-ITERATION-2.md](./PLAN-ITERATION-2.md) for full implementation details.

---

## Key Corrections from Previous Plan

| Issue | Before | After |
|-------|--------|-------|
| medical-flagging skill | In `.claude/skills/` | Removed - agent uses `@tool` decorator instead |
| Backend folder | `app/` | `src/` (consistency with frontend) |
| CLAUDE.md | Root only | Root + FE-specific + BE-specific |
| Package manager | pip | uv |
| Python version | 3.11 | 3.12 |
| Agent tools | Vague | Proper `@tool` + `create_sdk_mcp_server()` |
| Structured output | Manual parsing | `output_format` with JSON schema |
