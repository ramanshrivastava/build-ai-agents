  # SCOPE-V1: AI Doctor Assistant - Minimal E2E

> **Goal:** Working end-to-end system without tools - agent receives full patient record, returns structured briefing.
> **Status:** Planning
> **Created:** February 5, 2026

---

## V1 Constraints (What's OUT)

| Feature | V1 Status | Deferred To |
|---------|-----------|-------------|
| Agent tools (MCP) | ❌ Out | V2 |
| Drug interaction DB | ❌ Out | V2 |
| Langfuse observability | ❌ Out | V2 |
| SSE streaming | ❌ Out | V2 |
| Authentication | ❌ Out | V2+ |
| Rate limiting | ❌ Out | V2+ |
| Mobile responsive | ❌ Out | V2+ |
| Briefing caching | ❌ Out | V2+ |

---

## V1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         V1 Data Flow                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐     ┌──────────┐     ┌──────────────────────────┐ │
│  │ Frontend │────▶│ FastAPI  │────▶│ BriefingService          │ │
│  │ (React)  │     │ (BE)     │     │                          │ │
│  └──────────┘     └──────────┘     │  ┌────────────────────┐  │ │
│       ▲                │           │  │ Claude Opus 4.6    │  │ │
│       │                │           │  │ (configurable)     │  │ │
│       │                ▼           │  │ System: Clinical   │  │ │
│       │           ┌──────────┐     │  │ User: Patient JSON │  │ │
│       │           │ Postgres │     │  │ Output: Briefing   │  │ │
│       │           │ (Docker) │     │  └────────────────────┘  │ │
│       │           └──────────┘     └──────────────────────────┘ │
│       │                                        │                 │
│       └────────────────────────────────────────┘                 │
│                    PatientBriefing (JSON)                        │
└─────────────────────────────────────────────────────────────────┘
```

### Key Simplifications in V1

1. **No Tools** - Agent receives full patient record in user message, reasons about it directly
2. **No Streaming** - Simple request/response, frontend shows spinner
3. **All flags `source: "ai"`** - No rule-based flags yet (V2 adds tools for deterministic rules)
4. **Sync API** - POST /briefing blocks until complete

---

## Technology Stack

### Backend
| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| Python | 3.12 |
| Package Manager | uv |
| Database | PostgreSQL 16 (Docker Compose) |
| ORM | SQLAlchemy 2.0 async |
| Validation | Pydantic v2 |
| Config | pydantic-settings |
| AI | claude-opus-4-6 (configurable via `AI_MODEL` env var) via claude_agent_sdk |
| Linting | ruff |

### Frontend
| Component | Technology |
|-----------|------------|
| Framework | React 19 |
| Language | TypeScript (strict) |
| Build | Vite |
| Routing | React Router |
| State | @tanstack/react-query@5 |
| UI Components | shadcn/ui |
| Styling | Tailwind CSS |
| Icons | lucide-react |
| Linting | ESLint (flat config) + Prettier |

### Infrastructure
| Component | Technology |
|-----------|------------|
| Database | PostgreSQL via Docker Compose |
| BE Port | 8000 |
| FE Port | 5173 |

---

## Data Models

### Patient (Database)
```python
class Patient:
    id: int
    name: str                    # "Maria Garcia"
    date_of_birth: date          # 1957-03-15
    gender: str                  # "F"
    conditions: list[str]        # JSON - ["Type 2 Diabetes", "Hypertension"]
    medications: list[dict]      # JSON - [{"name": "Metformin", "dosage": "500mg", "frequency": "twice daily"}]
    labs: list[dict]             # JSON - [{"name": "HbA1c", "value": 7.2, "unit": "%", "date": "2024-01-15", "reference_range": {"min": 4.0, "max": 5.6}}]
    allergies: list[str]         # JSON - ["Penicillin", "Shellfish"]
    visits: list[dict]           # JSON - [{"date": "2024-01-15", "reason": "Annual checkup"}]
    created_at: datetime
    updated_at: datetime
```

> **Note:** Use `sqlalchemy.JSON` (not `dialects.postgresql.JSONB`). `JSON` maps to JSONB on PostgreSQL automatically and also works on SQLite for tests. V1 never queries inside JSON columns.

### PatientBriefing (Agent Output Schema)

The agent produces this via structured output. `generated_at` is NOT part of the agent schema — it is set server-side after a valid response.

```python
class Flag:
    category: Literal["labs", "medications", "screenings", "ai_insight"]
    severity: Literal["critical", "warning", "info"]
    title: str
    description: str
    source: Literal["ai"]  # V1: always "ai", V2 adds "tool:*"
    suggested_action: str | None

class Summary:
    one_liner: str
    key_conditions: list[str]
    relevant_history: str

class SuggestedAction:
    action: str
    reason: str
    priority: int  # 1 = highest

class PatientBriefing:
    flags: list[Flag]                    # 0-N flags
    summary: Summary
    suggested_actions: list[SuggestedAction]  # 3-5 actions
```

The API response wrapper adds `generated_at: datetime` server-side.

---

## API Endpoints

### Patients
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/patients` | List all patients |
| GET | `/api/v1/patients/{id}` | Get single patient |

### Briefings
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/patients/{id}/briefing` | Generate briefing (sync) |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |

### Error Responses
```python
class ErrorDetail:
    code: str       # "PATIENT_NOT_FOUND"
    message: str    # "Patient with ID 99 not found"
    details: dict   # {}
```

Raised via `HTTPException(status_code=404, detail=ErrorDetail(...).model_dump())`.

Status codes: 200 (success), 404 (patient not found), 500 (agent error)

---

## Frontend Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | Redirect | Redirect to /patients |
| `/patients/:id?` | PatientsPage | Sidebar list + detail area (optional `:id` param) |

> **Simplified routing:** Only 2 routes. PatientList reads URL, detail area reads `:id` param.

---

## UI Specifications

### Layout
```
┌─────────────────────────────────────────────────────────────────┐
│  🏥 AI Doctor Assistant                                          │
├────────────────┬────────────────────────────────────────────────┤
│                │                                                 │
│  SIDEBAR       │  MAIN AREA                                      │
│  (250px)       │                                                 │
│                │  ┌─────────────────────────────────────────┐   │
│  Patient List  │  │ Patient Name, Age Gender                │   │
│                │  │                                         │   │
│  ┌──────────┐  │  │ [✨ Generate Briefing]                  │   │
│  │ Card     │◄─┼──│                                         │   │
│  │ Selected │  │  │ ▼ Conditions (collapsible)              │   │
│  └──────────┘  │  │ ▼ Medications                           │   │
│  ┌──────────┐  │  │ ▼ Labs                                  │   │
│  │ Card     │  │  │ ▼ Allergies                             │   │
│  └──────────┘  │  │ ▼ Recent Visits                         │   │
│  ┌──────────┐  │  └─────────────────────────────────────────┘   │
│  │ Card     │  │                                                 │
│  └──────────┘  │                                                 │
│                │                                                 │
└────────────────┴────────────────────────────────────────────────┘
```

### Patient Card (Sidebar)
- Name, Age only: "John Smith, 67M"
- Age computed from `date_of_birth` via `calculateAge()` utility in `src/lib/utils.ts`
- Selected state: blue border + light blue background
- Hover state: subtle gray background
- Focus state: ring outline

### Generate Button States
1. **Idle:** "✨ Generate Briefing" (enabled)
2. **Loading:** "Generating briefing..." with spinner (disabled)
3. **Error:** Show error message + "Retry" button

### Briefing View (After Generation)
```
┌─────────────────────────────────────────────────────────────────┐
│ Generated just now                              [🔄 Regenerate] │
├─────────────────────────────────────────────────────────────────┤
│ ⚠️ FLAGS (3)                                                     │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 🔴 CRITICAL: HbA1c significantly elevated                   │ │
│ │ Current value 8.2% exceeds target of 7.0%                   │ │
│ │ → Consider medication adjustment                            │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 🟡 WARNING: Overdue for colonoscopy                         │ │
│ │ Last screening was 12 years ago                             │ │
│ │ → Schedule screening                                        │ │
│ └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ 📋 SUMMARY                                                       │
│ "67-year-old male with poorly controlled Type 2 Diabetes..."   │
│                                                                  │
│ Key Conditions: Diabetes, Hypertension, Hyperlipidemia          │
├─────────────────────────────────────────────────────────────────┤
│ ✅ SUGGESTED ACTIONS                                             │
│ 1. Review A1C trend and consider medication adjustment          │
│ 2. Schedule overdue colonoscopy screening                       │
│ 3. Check blood pressure control at this visit                   │
└─────────────────────────────────────────────────────────────────┘
```

### Flag Colors & Icons
- 🔴 Critical: Red background/border
- 🟡 Warning: Yellow/Amber background/border
- 🔵 Info: Blue background/border

Category icons (lucide-react):
- `labs` → `TestTube2`
- `medications` → `Pill`
- `screenings` → `ClipboardCheck`
- `ai_insight` → `Lightbulb`

### Lab Display Format
- Format: `HbA1c: 7.2% (4.0–5.6) · Jan 15, 2024`
- Out-of-range values: red text
- Normal values: default text color

### Collapsible Sections (Patient Details)
- Use HTML `<details>` element (simplest, no extra dependency)
- Default: all sections **open** (doctor wants to see everything at a glance)
- No animation for V1

### Timestamp Display
- "Generated just now" — use `Intl.RelativeTimeFormat` or simple utility function
- No external library needed (briefings aren't persisted in V1)

### Empty States
- No patient selected: centered "Select a patient to view their details"
- No conditions on file: "No conditions on file"
- No medications on file: "No medications on file"
- No lab results on file: "No lab results on file"
- No known allergies: "No known allergies"
- No recent visits: "No recent visits"

---

## Seed Data (5 Patients)

| # | Name | Age | Complexity | Key Conditions |
|---|------|-----|------------|----------------|
| 1 | Maria Garcia | 67F | Complex | Type 2 Diabetes, Hypertension, CKD Stage 3 |
| 2 | James Wilson | 45M | Moderate | Hypertension, Anxiety |
| 3 | Sarah Chen | 32F | Healthy | None (annual checkup) |
| 4 | Robert Johnson | 72M | Complex | CHF, Atrial Fibrillation, COPD |
| 5 | Emily Thompson | 55F | Moderate | Hypothyroidism, Osteoporosis |

Each patient will have:
- 2-5 medications (appropriate to conditions)
- 3-8 lab results (mix of normal and abnormal)
- 0-3 allergies
- 3-5 recent visits

---

## Project Structure

### Backend (`backend/`)
```
backend/
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, CORS, lifespan, routers
│   ├── config.py               # pydantic-settings config
│   ├── database.py             # SQLAlchemy async setup
│   ├── models/
│   │   ├── __init__.py
│   │   ├── orm.py              # SQLAlchemy Patient model
│   │   └── schemas.py          # Pydantic request/response/error models
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── patients.py         # Patient endpoints
│   │   └── briefings.py        # Briefing endpoint
│   └── services/
│       ├── __init__.py
│       ├── patient_service.py  # Patient CRUD
│       └── briefing_service.py # Agent orchestration
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Fixtures
│   ├── test_patients.py
│   └── test_briefings.py
├── seed.py                     # Database seeding script
├── pyproject.toml
├── uv.lock
└── .env.example
```

### Frontend (`frontend/`)
```
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── components/
│   │   ├── ui/                 # shadcn/ui components
│   │   ├── layout/
│   │   │   ├── Header.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── MainArea.tsx
│   │   ├── patients/
│   │   │   ├── PatientCard.tsx
│   │   │   ├── PatientList.tsx
│   │   │   └── PatientDetails.tsx
│   │   └── briefing/
│   │       ├── BriefingView.tsx    # All sections: flags, summary, actions
│   │       └── FlagCard.tsx        # Severity coloring logic
│   ├── pages/
│   │   └── PatientsPage.tsx
│   ├── hooks/
│   │   ├── usePatients.ts
│   │   └── useBriefing.ts
│   ├── services/
│   │   └── api.ts
│   ├── types/
│   │   └── index.ts
│   └── lib/
│       └── utils.ts            # calculateAge(), cn(), etc.
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.app.json
├── vite.config.ts
├── tailwind.config.js
├── eslint.config.js
├── .prettierrc
└── .env.example
```

---

## Task Breakdown

### Legend
- `[S]` Small (~15-30 min)
- `[M]` Medium (~30-60 min)
- `[L]` Large (~60-90 min)
- `→ verify:` How to verify task is complete
- `⛔ blocked by:` Task dependencies

---

## 1. Infrastructure Setup

### 1.1 Docker Compose [S]
- [x] Create `docker-compose.yml` in repo root with PostgreSQL 16
- [x] Add volume for data persistence
- → verify: `docker-compose up -d && docker ps | grep postgres`

### 1.2 Environment Files [S]
- [x] Create `backend/.env.example` with required variables:
  ```
  # Optional locally (SDK proxies through Claude Code CLI).
  # Required for production/deployed use.
  ANTHROPIC_API_KEY=
  AI_MODEL=claude-opus-4-6
  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/doctor_assistant
  DEBUG=false
  ```
- [x] Create `frontend/.env.example` with `VITE_API_URL=http://localhost:8000`
- → verify: Files exist with documented variables

---

## 2. Backend: Database & Models

### 2.1 Database Setup [M]
- [x] Add dependencies: `uv add sqlalchemy asyncpg pydantic-settings`
- [x] Create `src/config.py` with Settings class (includes `ai_model: str = "claude-opus-4-6"`)
- [x] Create `src/database.py` with async engine and session
- → verify: `uv run python -c "from src.database import engine; print(engine)"`
- ⛔ blocked by: 1.1

### 2.2 Patient ORM Model [M]
- [x] Create `src/models/orm.py` with Patient model
- [x] Use `sqlalchemy.JSON` columns for conditions, medications, labs, allergies, visits
- [x] Add timestamps (created_at, updated_at)
- → verify: Model imports without error
- ⛔ blocked by: 2.1

> **Important:** Use `sqlalchemy.JSON`, not `sqlalchemy.dialects.postgresql.JSONB`. `JSON` maps to JSONB on PostgreSQL automatically and works on SQLite for tests.

### 2.3 Pydantic Schemas [M]
- [x] Create `src/models/schemas.py`
- [x] Define PatientResponse, LabResult, Medication, Visit schemas
- [x] Define Flag, Summary, SuggestedAction, PatientBriefing schemas (agent output — no `generated_at`)
- [x] Define BriefingResponse wrapper (adds `generated_at: datetime` server-side)
- [x] Define ErrorDetail(code, message, details) schema
- → verify: All schemas import and validate test data
- ⛔ blocked by: 2.2

### 2.4 Seed Data Script [L]
- [x] Create `seed.py` with 5 realistic patients
- [x] Include varied conditions, meds, labs per specification
- [x] Table creation strategy: drop-and-recreate on each run (simple for V1 POC):
  ```python
  async with engine.begin() as conn:
      await conn.run_sync(Base.metadata.drop_all)
      await conn.run_sync(Base.metadata.create_all)
  ```
- [x] Entry point: `asyncio.run(main())`
- [x] No Alembic for V1
- → verify: `uv run python seed.py && uv run python -c "from src.database import ..."`
- ⛔ blocked by: 2.2

---

## 3. Backend: Patient API

### 3.1 Patient Service [M]
- [x] Create `src/services/patient_service.py`
- [x] Implement `get_all_patients(session: AsyncSession)` async function
- [x] Implement `get_patient_by_id(session: AsyncSession, id: int)` async function
- [x] Service functions accept session as parameter (not class-based)
- → verify: Service functions work in isolation
- ⛔ blocked by: 2.3

### 3.2 Patient Router [M]
- [x] Create `src/routers/patients.py`
- [x] Router pattern: `session: AsyncSession = Depends(get_session)`
- [x] Implement `GET /api/v1/patients` endpoint
- [x] Implement `GET /api/v1/patients/{id}` endpoint
- [x] Error handling: raise `HTTPException(status_code=404, detail=ErrorDetail(...).model_dump())`
- → verify: `curl http://localhost:8000/api/v1/patients`
- ⛔ blocked by: 3.1

### 3.3 Main App Setup [M]
- [x] Update `src/main.py` with CORS middleware:
  ```python
  CORSMiddleware(allow_origins=["http://localhost:5173"], allow_methods=["*"],
                 allow_credentials=True, allow_headers=["*"])
  ```
- [x] Add lifespan for DB connection:
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      yield
      await engine.dispose()
  ```
- [x] Add patient router
- [x] Add health check endpoint
- → verify: `uv run uvicorn src.main:app --reload` starts without error
- ⛔ blocked by: 3.2

---

## 4. Backend: Briefing Agent

### 4.1 Agent Dependencies [S]
- [x] Verify `claude-agent-sdk` is in deps (already present in `pyproject.toml`)
- [x] Verify `asyncpg` is in deps (added in this plan)
- [x] Add `ANTHROPIC_API_KEY` to `.env.example` as optional with comment:
  ```
  # Optional locally (SDK proxies through Claude Code CLI).
  # Required for production/deployed use.
  ANTHROPIC_API_KEY=
  ```
- → verify: `uv run python -c "import claude_agent_sdk"` succeeds
- ⛔ blocked by: 2.1

### 4.2 System Prompt [M]
- [x] Create detailed clinical system prompt in `briefing_service.py`
- [x] Pass via `ClaudeAgentOptions(system_prompt="...")`, not as a message
- [x] Include: role definition, flag categories and severity guidelines, output expectations
- [x] Do NOT include JSON schema instructions (structured output handles this automatically)
- → verify: Prompt is clear and complete
- ⛔ blocked by: 4.1

### 4.3 Briefing Service [L]
- [x] Create `src/services/briefing_service.py`
- [x] Implement `generate_briefing(patient: Patient) -> BriefingResponse`
- [x] Use `query()` function (async iterator), NOT a client class
- [x] Send full patient JSON as user message
- [x] Use structured output: `output_format={"type": "json_schema", "schema": PatientBriefing.model_json_schema()}`
- [x] Set `max_turns=1` (no tools in V1)
- [x] Set `permission_mode="bypassPermissions"` (server-side, no interactive prompts)
- [x] Check `isinstance(message, ResultMessage)` and `message.subtype == "success"`
- [x] Access `message.structured_output` (dict) → `PatientBriefing.model_validate(...)`
- [x] Handle `message.subtype == "error_max_structured_output_retries"`
- [x] Handle error types: `CLINotFoundError`, `CLIConnectionError`, `ProcessError`, `CLIJSONDecodeError`
- [x] Set `generated_at` server-side after receiving valid response
- → verify: Can generate briefing for seeded patient
- ⛔ blocked by: 4.2, 2.3

### 4.4 Briefing Router [M]
- [x] Create `src/routers/briefings.py`
- [x] Implement `POST /api/v1/patients/{id}/briefing`
- [x] Router pattern: `session: AsyncSession = Depends(get_session)`
- [x] Return 404 if patient not found
- [x] Return 500 with error details if agent fails
- → verify: `curl -X POST http://localhost:8000/api/v1/patients/1/briefing`
- ⛔ blocked by: 4.3, 3.2

---

## 5. Backend: Testing

### 5.1 Test Setup [M]
- [x] Dev dependencies already in pyproject.toml: pytest, pytest-asyncio, httpx, pytest-mock, aiosqlite
- [x] Create `tests/conftest.py` with fixtures
- [x] Set up test database (SQLite in-memory via aiosqlite for speed)
- → verify: `uv run pytest --collect-only`
- ⛔ blocked by: 3.3

### 5.2 Patient API Tests [M]
- [x] Create `tests/test_patients.py`
- [x] Test GET /patients returns list
- [x] Test GET /patients/{id} returns patient
- [x] Test GET /patients/{id} returns 404 for invalid ID
- → verify: `uv run pytest tests/test_patients.py -v`
- ⛔ blocked by: 5.1

### 5.3 Briefing API Tests [M]
- [x] Create `tests/test_briefings.py`
- [x] Mock the agent call (don't hit real API)
- [x] Test POST /briefing returns valid structure
- [x] Test POST /briefing returns 404 for invalid patient
- → verify: `uv run pytest tests/test_briefings.py -v`
- ⛔ blocked by: 5.1, 4.4

---

## 6. Frontend: Setup & Structure

### 6.1 Dependencies [M]
- [x] Install: `npm i @tanstack/react-query@5 react-router-dom lucide-react`
- [x] Initialize shadcn/ui: `npx shadcn-ui@latest init`
- [x] Add shadcn components: `npx shadcn-ui@latest add button card badge collapsible skeleton`
- [x] Configure `@/` path alias in `tsconfig.app.json` paths (required by shadcn/ui)
- → verify: `npm run dev` works with new deps
- ⛔ blocked by: none (can start immediately)

### 6.2 Tailwind & shadcn Config [M]
- [x] Configure tailwind.config.js for shadcn
- [x] Set up CSS variables for theme colors
- [x] Add flag severity color utilities (red, yellow, blue variants)
- [x] Configure `@/` alias in `vite.config.ts` resolve.alias
- → verify: Tailwind classes work in components

### 6.3 TypeScript Types [M]
- [x] Update `src/types/index.ts`
- [x] Define Patient, LabResult, Medication, Visit interfaces
- [x] Define Flag (with `category: 'labs' | 'medications' | 'screenings' | 'ai_insight'`), BriefingSummary, SuggestedAction, PatientBriefing types
- [x] Ensure `BriefingSummary.relevant_history` is required (not optional)
- [x] Ensure `SuggestedAction.reason` is required (not optional)
- [x] Add `generated_at: string` to `PatientBriefing` (set by server, not agent)
- [x] Define API error response types
- → verify: Types compile without error
- ⛔ blocked by: 6.1

### 6.4 API Client [M]
- [x] Create `src/services/api.ts`
- [x] Implement `getPatients(): Promise<Patient[]>`
- [x] Implement `getPatient(id): Promise<Patient>`
- [x] Implement `generateBriefing(id): Promise<PatientBriefing>` with 120s timeout (AbortController-based, increased from 60s after E2E testing)
- [x] Add error handling with typed errors
- → verify: Functions have correct types
- ⛔ blocked by: 6.3

### 6.5 React Query Setup [S]
- [x] Create QueryClient in main.tsx
- [x] Create `src/hooks/usePatients.ts` with useQuery
- [x] Create `src/hooks/useBriefing.ts` with useMutation
- → verify: Hooks compile and have correct types
- ⛔ blocked by: 6.4

### 6.6 Router Setup [S]
- [x] Configure React Router in App.tsx
- [x] Create routes: `/` (redirect to /patients), `/patients/:id?` (single route with optional param)
- [x] PatientList reads URL, detail area reads `:id` param
- → verify: Navigation works between routes
- ⛔ blocked by: 6.1

---

## 7. Frontend: Layout Components

### 7.1 Header Component [S]
- [x] Create `src/components/layout/Header.tsx`
- [x] Add logo placeholder and "AI Doctor Assistant" title
- [x] Style with Tailwind (fixed top, border-bottom)
- → verify: Header renders correctly
- ⛔ blocked by: 6.2

### 7.2 Sidebar Component [M]
- [x] Create `src/components/layout/Sidebar.tsx`
- [x] Fixed width (250px), full height
- [x] Accept children (patient list)
- → verify: Sidebar renders with correct dimensions
- ⛔ blocked by: 6.2

### 7.3 Main Layout [M]
- [x] Create `src/components/layout/MainArea.tsx`
- [x] Combine Header + Sidebar + Main content area
- [x] Handle responsive behavior (desktop only)
- → verify: Layout structure matches specification
- ⛔ blocked by: 7.1, 7.2

---

## 8. Frontend: Patient Components

### 8.1 Patient Card [M]
- [x] Create `src/components/patients/PatientCard.tsx`
- [x] Display name and age (e.g., "John Smith, 67M")
- [x] Compute age from `date_of_birth` via `calculateAge(dob: string): number` in `src/lib/utils.ts`
- [x] Selected state: blue border + light blue background
- [x] Hover state: subtle gray background
- [x] Focus state: ring outline
- [x] Handle click to select
- → verify: Card renders and selection works
- ⛔ blocked by: 6.2

### 8.2 Patient List [M]
- [x] Create `src/components/patients/PatientList.tsx`
- [x] Use usePatients hook to fetch data
- [x] Show loading skeleton while fetching
- [x] Show error state on fetch failure (message + retry)
- [x] Map patients to PatientCard components
- [x] Handle selection state
- → verify: List renders with data from API
- ⛔ blocked by: 8.1, 6.5

### 8.3 Patient Details - Data Sections [L]
- [x] Create `src/components/patients/PatientDetails.tsx`
- [x] Add collapsible sections using HTML `<details>` element: Conditions, Medications, Labs, Allergies, Visits
- [x] Default: all sections **open** (no animation for V1)
- [x] Show patient name, age, gender at top
- [x] Handle empty states ("No conditions on file", etc.)
- [x] Lab display format: `HbA1c: 7.2% (4.0–5.6) · Jan 15, 2024`
- [x] Out-of-range lab values: red text. Normal values: default text color
- → verify: All sections render correctly
- ⛔ blocked by: 6.2, 6.3

### 8.4 Generate Button [M]
- [x] Add "Generate Briefing" button to PatientDetails
- [x] Position at top of detail area
- [x] Handle loading state (spinner + disabled)
- [x] Handle error state (show error message + retry button)
- [x] Wire up to useBriefing mutation
- → verify: Button triggers API call
- ⛔ blocked by: 8.3, 6.5

---

## 9. Frontend: Briefing Components

### 9.1 Flag Card [M]
- [x] Create `src/components/briefing/FlagCard.tsx`
- [x] Accept flag data (category, severity, title, description, action)
- [x] Color-code by severity (red/yellow/blue)
- [x] Show category icon: `labs` → TestTube2, `medications` → Pill, `screenings` → ClipboardCheck, `ai_insight` → Lightbulb
- [x] Show suggested action if present
- → verify: Flag renders with correct colors
- ⛔ blocked by: 6.2, 6.3

### 9.2 Briefing View [L]
- [x] Create `src/components/briefing/BriefingView.tsx`
- [x] Compose all sections inline: timestamp, regenerate button, flags, summary, actions
- [x] **Flags section:** map flags to FlagCard components, handle empty flags gracefully
- [x] **Summary section:** display one-liner prominently, show key conditions as badges, show relevant history paragraph
- [x] **Actions section:** numbered list of actions with priority indicator and reason
- [x] Show "Generated just now" timestamp (use `Intl.RelativeTimeFormat` or simple utility)
- [x] Add Regenerate button that triggers new generation
- → verify: Full briefing displays correctly
- ⛔ blocked by: 9.1, 6.5

---

## 10. Frontend: Page Integration

### 10.1 Patients Page [L]
- [x] Create `src/pages/PatientsPage.tsx`
- [x] Integrate Sidebar with PatientList
- [x] Show PatientDetails in main area when patient selected
- [x] Show empty state when no patient selected: centered "Select a patient to view their details"
- [x] Manage selected patient state (from URL `:id` param)
- [x] Show BriefingView when briefing generated
- [ ] Add error boundary wrapping the page
- → verify: Full page flow works
- ⛔ blocked by: 8.2, 8.4, 9.2, 7.3

---

## 11. Integration & Polish

### 11.1 End-to-End Integration [M]
- [x] Test full flow: list → select → generate → view
- [x] Fix any integration issues
- → verify: Full E2E works with real data
- ⛔ blocked by: 4.4, 10.1

### 11.2 README Update [M]
- [ ] Write setup instructions (Docker, BE, FE)
- [ ] Document environment variables
- [ ] Add screenshots of working app
- → verify: New developer can set up from README
- ⛔ blocked by: 11.1

---

## Execution Sequence

### Phase 1: Infrastructure (Do First)
```
1.1 Docker Compose ──┐
1.2 Environment Files┘
```

### Phase 2: Backend Core (BE Worktree)
```
2.1 Database Setup ─────┬─▶ 2.2 Patient ORM ─▶ 2.3 Pydantic Schemas ─▶ 2.4 Seed Data
                        │
4.1 Agent Dependencies ─┘

2.3 ─▶ 3.1 Patient Service ─▶ 3.2 Patient Router ─▶ 3.3 Main App Setup
```

### Phase 3: Backend Agent (BE Worktree)
```
4.1 ─▶ 4.2 System Prompt ─▶ 4.3 Briefing Service ─▶ 4.4 Briefing Router
```

### Phase 4: Backend Tests (BE Worktree)
```
3.3 ─▶ 5.1 Test Setup ─▶ 5.2 Patient Tests
                        ─▶ 5.3 Briefing Tests (after 4.4)
```

### Phase 5: Frontend Structure (FE Worktree - Can Start Early)
```
6.1 Dependencies ─▶ 6.2 Tailwind Config
```

### Phase 6: Frontend Components (FE Worktree - Parallel after 6.1+6.2)
```
Parallel A: 6.3 Types | 6.6 Router | 7.1 Header + 7.2 Sidebar
Parallel B: 6.4 API → 6.5 Hooks | 8.1 PatientCard | 9.1 FlagCard
Parallel C: 8.2 Patient List | 8.3 Patient Details | 7.3 Layout shell
Parallel D: 8.4 Generate Button | 9.2 BriefingView
Final: 10.1 PatientsPage
```

### Phase 7: Integration (Both Worktrees)
```
11.1 E2E Integration ─▶ 11.2 README
```

---

## Parallel Execution Plan

### BE Agent (in `ai-doctor-assistant-backend/`)
Execute in order:
1. Tasks 1.1, 1.2 (Infrastructure)
2. Tasks 2.1 → 2.4 (Database)
3. Tasks 3.1 → 3.3 (Patient API)
4. Tasks 4.1 → 4.4 (Briefing Agent)
5. Tasks 5.1 → 5.3 (Tests)

### FE Agent (in `ai-doctor-assistant-frontend/`)
Execute:
1. Tasks 6.1 → 6.2 (Setup)
2. Parallel: 6.3, 6.6, 7.1, 7.2
3. Parallel: 6.4 → 6.5, 8.1, 9.1
4. Parallel: 8.2, 8.3, 7.3
5. Parallel: 8.4, 9.2
6. Task 10.1 (Page Integration)

### Integration (After Both Complete)
1. Task 11.1 (E2E Integration)
2. Task 11.2 (README)

---

## Success Criteria for V1

- [ ] Docker Compose starts PostgreSQL successfully
- [ ] Backend serves patient list at GET /api/v1/patients
- [ ] Backend generates briefing at POST /api/v1/patients/{id}/briefing
- [ ] Generated briefing has valid structure (flags, summary, actions)
- [x] Frontend displays patient list in sidebar
- [x] Clicking patient shows their details
- [x] "Generate Briefing" button triggers agent call
- [x] Briefing displays with colored flags
- [x] Regenerate button works
- [x] Error states handled gracefully
- [ ] README has setup instructions

---

## Verification Commands

### Infrastructure
```bash
docker-compose up -d
docker ps | grep postgres  # Should show running
```

### Backend
```bash
cd backend
uv run python seed.py  # Seed database
uv run uvicorn src.main:app --reload
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/patients
curl http://localhost:8000/api/v1/patients/1
curl -X POST http://localhost:8000/api/v1/patients/1/briefing
uv run pytest -v
```

### Frontend
```bash
cd frontend
npm run dev
# Open http://localhost:5173
# Click patient → Generate Briefing → View result
npm run lint
npm run build  # Verify production build works
```