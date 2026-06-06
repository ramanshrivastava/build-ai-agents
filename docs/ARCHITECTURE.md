# AI Doctor Assistant - Architecture

## System Overview

```mermaid
flowchart TB
    subgraph Frontend["Frontend (React + TypeScript)"]
        UI[Patient List UI]
        BriefingView[Briefing View]
        API_Client[API Client]
    end

    subgraph Backend["Backend (FastAPI + Python 3.12)"]
        API[REST API]
        PatientService[Patient Service]
        BriefingService[Briefing Service]
        DB[(PostgreSQL)]
    end

    subgraph Agent["AI Agent (Claude Agent SDK)"]
        BriefingAgent[Briefing Agent]

        subgraph Tools["Agent Tools"]
            GuidelineTool[search_clinical_guidelines]
        end
    end

    subgraph Managed["Optional Managed Runtime"]
        ManagedSession[Claude Managed Agents Session]
        ManagedTool[Custom Tool Events]
    end

    subgraph Observability["Observability"]
        Langfuse[Langfuse Tracing]
    end

    UI --> API_Client
    BriefingView --> API_Client
    API_Client -->|HTTP| API

    API --> PatientService
    API --> BriefingService
    PatientService --> DB

    BriefingService -->|patient record| BriefingAgent
    BriefingAgent -->|calls| GuidelineTool
    BriefingAgent -->|structured output| BriefingService
    BriefingService -->|optional /briefing/managed| ManagedSession
    ManagedSession -->|agent.custom_tool_use| ManagedTool
    ManagedTool --> GuidelineTool

    BriefingAgent -.->|traces| Langfuse
    Tools -.->|traces| Langfuse
```

## Data Flow: Generate Briefing

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as FastAPI
    participant PS as PatientService
    participant BS as BriefingService
    participant Agent as BriefingAgent
    participant Tools as Guideline Search Tool
    participant LF as Langfuse

    FE->>API: POST /api/v1/patients/{id}/briefing
    API->>PS: get_patient(id)
    PS-->>API: Patient record
    API->>BS: generate_briefing(patient)

    BS->>Agent: Full patient record + system prompt

    Note over Agent: Agent reasons about patient

    Agent->>Tools: search_clinical_guidelines(query)
    Tools-->>Agent: Retrieved guideline chunks with source IDs

    Note over Agent: Agent synthesizes briefing

    Agent-->>BS: Structured PatientBriefing

    BS->>LF: Log trace + tool calls
    BS-->>FE: JSON BriefingResponse
```

## Component Details

### Frontend (React + TypeScript + Vite)

| Component | Purpose |
|-----------|---------|
| `PatientList` | Display list of patients for the day |
| `PatientCard` | Individual patient card in the list |
| `PatientDetails` | Patient info + "Generate Briefing" button |
| `GeneratingView` | Animated tool call progress while generating |
| `ToolCallStep` | Individual tool call status (pending/running/done) |
| `BriefingView` | Display AI-generated briefing with flags |
| `FlagCard` | Visual component for each flag (color-coded by severity) |
| `api.ts` | Centralized API client (sync briefing endpoints; SSE is V2+) |

### Backend (FastAPI + Python 3.12)

| Module | Purpose |
|--------|---------|
| `routers/patients.py` | Patient CRUD endpoints |
| `routers/briefings.py` | Briefing generation endpoint |
| `services/patient_service.py` | Patient data access |
| `services/briefing_service.py` | Orchestrates agent calls |
| `services/managed_briefing_service.py` | Optional Claude Managed Agents runtime path |
| `agents/briefing_agent.py` | Claude Agent SDK configuration |
| `agents/tools.py` | Clinical guideline search tool definition |

### AI Agent Tools

| Tool | Input | Output | Logic |
|------|-------|--------|-------|
| `search_clinical_guidelines` | Query, optional specialty, max results | XML-formatted guideline chunks with source IDs | Embeds query, searches Qdrant, formats citations |

### Structured Output Schema

```json
{
  "flags": [
    {
      "category": "labs|medications|screenings|ai_insight",
      "severity": "critical|warning|info",
      "title": "string",
      "description": "string",
      "source": "ai",
      "suggested_action": "string"
    }
  ],
  "summary": {
    "one_liner": "string",
    "key_conditions": ["string"],
    "relevant_history": "string"
  },
  "suggested_actions": [
    {
      "action": "string",
      "reason": "string",
      "priority": 1
    }
  ]
}
```

## Key Design Decisions

### 1. Agent-with-Tools Pattern

**Decision:** Give agent full patient record and let it call the clinical guideline search tool as needed.

**Rationale:**
- Agent can reason about *what* to check based on patient context
- Tool implementation remains testable
- More flexible than rigid rules-first pipeline
- AI can spot patterns rules might miss

**Tradeoff:** Agent orchestration is non-deterministic, but tool outputs are deterministic.

### 2. Source Tagging

Every flag currently uses `source: "ai"`. Citations in descriptions point to retrieved guideline source IDs such as `[1]`.

**Rationale:** Auditability for healthcare compliance.

### 3. Structured Output

Use Claude Agent SDK's `output_format` with JSON schema.

**Rationale:**
- Guaranteed valid JSON
- Pydantic validation on backend
- Type-safe frontend consumption

### 4. Langfuse Observability

All agent interactions traced via hooks.

**Rationale:**
- Debug agent reasoning
- Monitor tool usage patterns
- Audit trail for compliance

### 5. On-Demand Briefing Generation

**Decision:** Briefing is generated on user request, not automatically when patient is selected.

**Rationale:**
- Avoids unnecessary API calls (cost + latency)
- User controls when to trigger AI generation
- Keeps the sync API simple while the frontend shows a loading state

---

## UX Flow: Generate Briefing

### State 1: Patient Selected (no briefing yet)
```
┌─────────────────────────────────────────┐
│  John Smith, 67M                        │
│  ─────────────────────────              │
│  Conditions: Diabetes, Hypertension     │
│  Medications: Metformin, Lisinopril     │
│  Last Visit: Jan 15, 2024               │
│                                         │
│      ┌──────────────────────┐           │
│      │ ✨ Generate Briefing │           │
│      └──────────────────────┘           │
│                                         │
└─────────────────────────────────────────┘
```

### State 2: Generating (V2+ vision — V1 shows a spinner instead of live tool calls)
```
┌─────────────────────────────────────────┐
│  John Smith, 67M                        │
│  ─────────────────────────              │
│                                         │
│  🔄 Generating briefing...              │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ ✓ check_lab_thresholds          │    │
│  │   Found 2 flags                 │    │
│  ├─────────────────────────────────┤    │
│  │ ✓ check_drug_interactions       │    │
│  │   No interactions found         │    │
│  ├─────────────────────────────────┤    │
│  │ ⏳ check_overdue_screenings     │    │
│  │   Running...                    │    │
│  └─────────────────────────────────┘    │
│                                         │
└─────────────────────────────────────────┘
```

### State 3: Briefing Ready
```
┌─────────────────────────────────────────┐
│  John Smith, 67M                        │
│  ─────────────────────────              │
│                                         │
│  ⚠️ Flags (3)                           │
│  ┌─────────────────────────────────┐    │
│  │ 🔴 HbA1c elevated (8.2%)        │    │
│  │    Source: tool:check_labs      │    │
│  └─────────────────────────────────┘    │
│                                         │
│  📋 Summary                             │
│  "Diabetic patient with suboptimal      │
│   glycemic control..."                  │
│                                         │
│  ✅ Suggested Actions                   │
│  1. Review A1C trend                    │
│  2. Check foot exam status              │
│                                         │
│      ┌──────────────────────┐           │
│      │ 🔄 Regenerate        │           │
│      └──────────────────────┘           │
└─────────────────────────────────────────┘
```

---

## SSE Event Stream Format (V2+ — not implemented)

> [!NOTE]
> **V1 ships a synchronous API.** `POST /api/v1/patients/{id}/briefing` returns a complete
> `BriefingResponse` JSON body (see `backend/src/routers/briefings.py`); the frontend shows a
> loading state while waiting (Key Design Decision 5). The SSE format below is the V2+ vision
> for streaming tool-call progress and does not change the sync endpoint's behavior.

In V2+, the backend would stream tool call progress via Server-Sent Events:

```
event: tool_start
data: {"tool": "check_lab_thresholds", "status": "running"}

event: tool_complete
data: {"tool": "check_lab_thresholds", "status": "done", "result_count": 2}

event: tool_start
data: {"tool": "check_drug_interactions", "status": "running"}

event: tool_complete
data: {"tool": "check_drug_interactions", "status": "done", "result_count": 0}

event: tool_start
data: {"tool": "check_overdue_screenings", "status": "running"}

event: tool_complete
data: {"tool": "check_overdue_screenings", "status": "done", "result_count": 1}

event: complete
data: {"briefing": {...full PatientBriefing object...}}
```

---

## Implementation Plan

> [!NOTE]
> Historical planning artifact. Where steps below mention SSE streaming or live tool-call
> animation, V1 shipped the synchronous endpoint instead (see Key Design Decision 5).

### Implementation Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data source | **PostgreSQL from start** | Cloud-ready from day 1, same DB engine for dev and prod |
| Local DB | **Docker Compose** | PostgreSQL container for local development |
| Cloud DB | **Google Cloud SQL** | Managed PostgreSQL on GCP for production |
| Tool complexity | **Simple thresholds** | Basic lab ranges to prove pattern works, expand later |
| UI approach | **Polished design** | Invest in good UI/UX from start for demo quality |

### Why PostgreSQL over SQLite?

| Aspect | SQLite | PostgreSQL |
|--------|--------|------------|
| Architecture | File-based | Client-server |
| Cloud Run/GKE | ❌ Each container gets own file | ✅ All instances share same DB |
| Data persistence | ❌ Lost on container restart | ✅ Managed by Cloud SQL |
| Horizontal scaling | ❌ Single writer | ✅ Multiple connections |
| Dev/Prod parity | ❌ Different engines | ✅ Same engine everywhere |

### Local Development: Docker Compose

```yaml
# docker-compose.yml (in repo root)
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: doctor
      POSTGRES_PASSWORD: doctor
      POSTGRES_DB: doctor_assistant
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

**Setup commands:**
```bash
# Start PostgreSQL
docker-compose up -d

# Verify running
docker ps | grep postgres

# Connection string for backend
postgresql+asyncpg://doctor:doctor@localhost:5432/doctor_assistant
```

### Phase 1: Backend Tasks

**Location:** `ai-doctor-assistant-be-foundation/backend/`

#### 1. Database Setup
- `src/database.py` - SQLAlchemy async with asyncpg
- `src/models/orm.py` - Patient ORM model:
  ```python
  class Patient:
      id: int
      name: str
      date_of_birth: date
      gender: str
      conditions: list[str]      # JSONB - ["Type 2 Diabetes", "Hypertension"]
      medications: list[dict]    # JSONB - [{"name": "Metformin", "dosage": "500mg", "frequency": "twice daily"}]
      labs: list[dict]           # JSONB - [{"name": "HbA1c", "value": 7.2, "unit": "%", "date": "2024-01-15"}]
      allergies: list[str]       # JSONB
  ```
- **Dependency:** `uv add asyncpg` (not aiosqlite)
- `src/seed.py` - Seed script with 3-5 realistic patients

#### 2. Pydantic Schemas
- `src/models/schemas.py`:
  - `LabResult` - name, value, unit, date, reference_range
  - `Medication` - name, dosage, frequency, start_date
  - `Condition` - name, diagnosed_date, status
  - `Flag` - category, severity, title, description, source, suggested_action
  - `PatientBriefing` - flags, summary, suggested_actions
  - `PatientResponse` - full patient for API

#### 3. Deterministic Tools
- `src/agents/tools.py`:

```python
# Simple threshold examples
LAB_THRESHOLDS = {
    "glucose": {"high": 200, "low": 70},
    "HbA1c": {"high": 7.0},
    "eGFR": {"low": 60},
    "creatinine": {"high": 1.2},
}

DRUG_INTERACTIONS = [
    ("metformin", "contrast dye", "Hold metformin 48h before/after contrast"),
    ("warfarin", "NSAID", "Increased bleeding risk"),
    ("ACE inhibitor", "potassium supplement", "Risk of hyperkalemia"),
]

SCREENING_RULES = [
    {"name": "Colonoscopy", "min_age": 50, "frequency_years": 10},
    {"name": "Mammogram", "min_age": 40, "frequency_years": 2, "gender": "F"},
    {"name": "A1C check", "condition": "Diabetes", "frequency_months": 3},
]
```

#### 4. Briefing Agent
- `src/agents/briefing_agent.py`:
  - System prompt with clinical context
  - Tool registration via `create_sdk_mcp_server()`
  - Structured output schema from `PatientBriefing`
  - Langfuse hooks for PreToolUse/PostToolUse

#### 5. API Routes
- `src/routers/patients.py`:
  - `GET /api/v1/patients` - list all patients
  - `GET /api/v1/patients/{id}` - get single patient
- `src/routers/briefings.py`:
  - `POST /api/v1/patients/{id}/briefing` - generate briefing

### Phase 1: Frontend Tasks

**Location:** `ai-doctor-assistant-fe-foundation/frontend/`

#### 1. Dependencies
```bash
npm install @tanstack/react-query tailwindcss postcss autoprefixer lucide-react framer-motion
npx tailwindcss init -p
```

#### 2. Types
- `src/types/index.ts` - Mirror backend Pydantic schemas exactly
- `ToolCallEvent` - For SSE streaming updates

#### 3. API Client
- `src/services/api.ts`:
  - `getPatients(): Promise<Patient[]>`
  - `getPatient(id: number): Promise<Patient>`
  - `generateBriefing(id: number, onToolEvent: (event) => void): Promise<PatientBriefing>`
    - Uses EventSource for SSE streaming
    - Calls `onToolEvent` for each tool_start/tool_complete event
    - Returns full briefing on `complete` event

#### 4. Components (Polished Design)

| Component | Description |
|-----------|-------------|
| `PatientList/` | Sidebar with card-based patient list |
| `PatientCard/` | Name, age, key conditions badge, click to select |
| `PatientDetails/` | Patient info display + "Generate Briefing" button |
| `GeneratingView/` | Animated progress view showing tool calls live |
| `ToolCallStep/` | Single tool call row with status icon (⏳ pending, 🔄 running, ✓ done) |
| `BriefingView/` | Final briefing display with flags, summary, actions |
| `FlagCard/` | Severity-colored card (red=critical, yellow=warning, blue=info) with icon |
| `SummarySection/` | One-liner headline + key conditions pills |
| `ActionsSection/` | Numbered priority list of suggested actions |

#### 5. State Machine

```
┌──────────────────┐    click patient    ┌─────────────────┐
│  No Selection    │ ──────────────────► │ Patient Selected │
└──────────────────┘                     └────────┬────────┘
                                                  │
                                    click "Generate Briefing"
                                                  │
                                                  ▼
                                         ┌─────────────────┐
                                         │   Generating    │
                                         │  (show tools)   │
                                         └────────┬────────┘
                                                  │
                                         SSE: complete event
                                                  │
                                                  ▼
                                         ┌─────────────────┐
                                         │ Briefing Ready  │◄──┐
                                         └────────┬────────┘   │
                                                  │            │
                                         click "Regenerate"    │
                                                  └────────────┘
```

#### 6. Layout
```
┌─────────────────────────────────────────────────────────┐
│  AI Doctor Assistant                            [logo]  │
├──────────────┬──────────────────────────────────────────┤
│              │                                          │
│  Patient     │  [PatientDetails / GeneratingView /      │
│  List        │   BriefingView based on state]           │
│              │                                          │
│  [Card 1]    │  State: Patient Selected                 │
│  [Card 2] ←  │  ┌──────────────────────────────────┐    │
│  [Card 3]    │  │ John Smith, 67M                  │    │
│  [Card 4]    │  │ Conditions: Diabetes, HTN        │    │
│              │  │                                  │    │
│              │  │   [✨ Generate Briefing]         │    │
│              │  └──────────────────────────────────┘    │
│              │                                          │
└──────────────┴──────────────────────────────────────────┘
```

---

## Execution Order

```mermaid
flowchart LR
    subgraph BE["Backend (BE worktree)"]
        DB[1. Database + Seed] --> Models[2. Pydantic Models]
        Models --> Routes[3. Patient API Routes]
        Routes --> Tools[5. Deterministic Tools]
        Tools --> Agent[6. Briefing Agent]
        Agent --> SSE[7. SSE Streaming Endpoint]
    end

    subgraph FE["Frontend (FE worktree)"]
        Types[2. Types] --> APIClient[3. API Client]
        APIClient --> PatientList[4. PatientList + PatientDetails]
        PatientList --> SSEClient[8. SSE Client + GeneratingView]
        SSEClient --> BriefingView[9. BriefingView Component]
        BriefingView --> Polish[10. Polish & Animations]
    end

    Routes -.->|verify: curl| PatientList
    SSE -.->|verify: curl| SSEClient
```

**Parallel Development:**

1. **Backend first** (BE worktree)
   - Database + seed data
   - Pydantic models
   - Patient API routes
   - Verify: can fetch patients via curl

2. **Frontend parallel** (FE worktree)
   - Types + API client
   - PatientList + PatientCard
   - PatientDetails with "Generate Briefing" button (disabled initially)
   - Verify: can see patient list, select patient, see details

3. **Agent integration** (BE worktree)
   - Tool definitions
   - Agent configuration with hooks
   - Briefing endpoint with SSE streaming
   - Verify: curl shows streaming tool events + final briefing

4. **Frontend generating state** (FE worktree)
   - SSE client in api.ts
   - GeneratingView with animated ToolCallStep components
   - Wire up button to trigger generation
   - Verify: see live tool call updates

5. **Frontend briefing display** (FE worktree)
   - BriefingView component
   - FlagCard with severity colors
   - SummarySection + ActionsSection
   - Regenerate button
   - Smooth transitions with framer-motion
   - Verify: full end-to-end flow works

---

## Success Criteria

- [ ] PostgreSQL database (via Docker Compose) with 3-5 seeded patients
- [ ] `GET /api/v1/patients` returns patient list
- [ ] `GET /api/v1/patients/{id}` returns single patient
- [ ] `POST /api/v1/patients/{id}/briefing` streams SSE events + final briefing
- [ ] Each flag has correct `source` tag (tool vs ai)
- [ ] Frontend displays patient list with polished cards
- [ ] Selecting patient shows details + "Generate Briefing" button
- [ ] Clicking generate shows animated tool call progress
- [ ] Tool calls appear live with status updates
- [ ] Briefing view shows flags with severity colors
- [ ] "Regenerate" button works to refresh briefing
- [ ] Langfuse dashboard shows tool call traces

---

## Verification Commands

### Database (Docker Compose)
```bash
# Start PostgreSQL container
docker-compose up -d

# Verify running
docker ps | grep postgres

# Connect to database (optional)
docker exec -it ai-doctor-assistant-db-1 psql -U doctor -d doctor_assistant

# Seed database
cd backend && uv run python -m src.seed
```

### Backend
```bash
cd backend && uv run uvicorn src.main:app --reload

# Test endpoints
curl http://localhost:8000/api/v1/patients
curl http://localhost:8000/api/v1/patients/1
curl -X POST http://localhost:8000/api/v1/patients/1/briefing
```

### Frontend
```bash
cd frontend && npm run dev
# Open http://localhost:5173
# Click patient → verify briefing loads with colored flags
```

### Observability
- Open Langfuse dashboard
- Find trace for briefing generation
- Verify tool calls appear with inputs/outputs
