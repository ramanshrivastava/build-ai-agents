# AI Doctor Assistant - POC Implementation Plan (Iteration 1)

> Created: February 4, 2026
> Status: Draft for approval

---

## Overview

A working prototype for an AI clinical assistant that helps doctors **before**, **during**, and **after** patient consultations.

| Aspect | Decision |
|--------|----------|
| **Tech Stack** | FastAPI (Python) + React |
| **Transcription** | Deepgram or AssemblyAI |
| **LLM** | Abstracted layer supporting Claude and OpenAI |
| **Data** | SQLite with JSON patient records |
| **Deployment** | Web app (browser-based) |
| **Methodology** | Test-Driven Development (TDD) |

---

## Product Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│     BEFORE      │     │     DURING      │     │      AFTER      │
│  Consultation   │ ──▶ │  Consultation   │ ──▶ │  Consultation   │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ • Read patient  │     │ • Record audio  │     │ • Transcribe    │
│   file          │     │   (passive)     │     │ • AI analysis   │
│ • AI summary    │     │ • No real-time  │     │ • Generate:     │
│ • Flags/alerts  │     │   processing    │     │   - Notes       │
│ • Suggested     │     │                 │     │   - ICD codes   │
│   actions       │     │                 │     │   - Rx          │
│                 │     │                 │     │ • Doctor review │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**Key Design Decision:** Batch processing (not real-time) - the AI processes the full conversation AFTER the consultation ends. This provides better context and simpler architecture.

---

## Deployment Strategy

```
Phase 1 (POC):   WEB APP (browser-based)
                 • Doctor opens in browser 
                 • Works on any OS, no installation
                 • Fastest to build and iterate

Phase 2 (Later): ELECTRON wrapper
                 • Same React code, packaged as desktop app
                 • Overlay/floating panel capability
                 • Better mic access, global shortcuts

```

**Voice Recording:** Uses browser's MediaRecorder API - works cross-platform (Windows, Mac, Linux) without any OS-specific code.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React)                         │
├───────────────┬─────────────────┬───────────────────────────┤
│ Before Screen │  During Screen  │      After Screen         │
│ • Patient list│  • Audio record │  • Review transcript      │
│ • AI summary  │  • Timer/status │  • AI-generated notes     │
│ • Flags/alerts│                 │  • ICD-10 codes           │
│               │                 │  • Rx suggestions         │
│               │                 │  • Approve/edit/save      │
└───────────────┴────────┬────────┴───────────────────────────┘
                         │ REST API
┌────────────────────────┴────────────────────────────────────┐
│                    Backend (FastAPI)                         │
├─────────────────────────────────────────────────────────────┤
│ Services:                                                    │
│ • PatientService - CRUD + AI summary generation              │
│ • ConsultationService - Audio upload, transcription          │
│ • ProcessingService - LLM analysis, code extraction          │
│ • LLMProvider - Abstract interface for Claude/OpenAI         │
└─────────────────────────────────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────────┐
│                   External Services                          │
├──────────────────┬──────────────────┬───────────────────────┤
│ Deepgram/        │ Claude/OpenAI    │ SQLite                │
│ AssemblyAI       │ (LLM)            │ (Patient data)        │
│ (Transcription)  │                  │                       │
└──────────────────┴──────────────────┴───────────────────────┘
```

---

## Project Structure

```
ai-doctor-assistant/
├── docs/                          # Documentation
│   └── PLAN-ITERATION-1.md        # This file
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app entry
│   │   ├── config.py             # Settings, API keys
│   │   ├── models/
│   │   │   ├── patient.py        # Patient data model
│   │   │   └── consultation.py   # Consultation model
│   │   ├── services/
│   │   │   ├── llm_provider.py   # Abstract LLM interface
│   │   │   ├── transcription.py  # Deepgram/AssemblyAI
│   │   │   ├── patient_summary.py
│   │   │   └── consultation_processor.py
│   │   ├── routers/
│   │   │   ├── patients.py
│   │   │   └── consultations.py
│   │   └── database.py           # SQLite setup
│   ├── data/
│   │   └── sample_patients.json  # Demo patient data
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── PatientList.tsx
│   │   │   ├── PatientSummary.tsx
│   │   │   ├── AudioRecorder.tsx
│   │   │   ├── ConsultationReview.tsx
│   │   │   └── Layout.tsx
│   │   ├── pages/
│   │   │   ├── BeforeConsultation.tsx
│   │   │   ├── DuringConsultation.tsx
│   │   │   └── AfterConsultation.tsx
│   │   ├── services/
│   │   │   └── api.ts
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
├── tests/                         # Shared test utilities
│   └── conftest.py
└── README.md
```

---

## Test-Driven Development (TDD) Approach

We follow the **Red-Green-Refactor** cycle for all implementation:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    RED      │ ──▶ │   GREEN     │ ──▶ │  REFACTOR   │
│ Write test  │     │ Make it     │     │ Clean up    │
│ (it fails)  │     │ pass        │     │ code        │
└─────────────┘     └─────────────┘     └─────────────┘
       ▲                                       │
       └───────────────────────────────────────┘
```

### Testing Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| **Backend Unit** | pytest | Service logic, models, utilities |
| **Backend Integration** | pytest + httpx | API endpoints, database |
| **Backend Mocks** | pytest-mock, responses | External APIs (LLM, transcription) |
| **Frontend Unit** | Vitest | Components, hooks, utilities |
| **Frontend Integration** | React Testing Library | User interactions, page flows |
| **E2E** | Playwright | Full user journeys (optional for POC) |

### Test Structure

```
backend/
├── tests/
│   ├── conftest.py              # Fixtures, test database setup
│   ├── unit/
│   │   ├── test_llm_provider.py
│   │   ├── test_patient_summary.py
│   │   └── test_consultation_processor.py
│   ├── integration/
│   │   ├── test_patients_api.py
│   │   └── test_consultations_api.py
│   └── mocks/
│       ├── mock_llm_responses.py
│       └── mock_transcription.py

frontend/
├── src/
│   ├── components/
│   │   ├── AudioRecorder.tsx
│   │   └── AudioRecorder.test.tsx    # Co-located tests
│   ├── pages/
│   │   ├── AfterConsultation.tsx
│   │   └── AfterConsultation.test.tsx
│   └── services/
│       ├── api.ts
│       └── api.test.ts
```

### TDD Workflow Per Feature

**Example: Implementing Patient Summary Service**

```
Step 1 (RED):    Write test_patient_summary.py
                 - test_generates_summary_with_conditions()
                 - test_flags_missing_vaccinations()
                 - test_handles_empty_patient_history()
                 → All tests FAIL (service doesn't exist)

Step 2 (GREEN):  Implement patient_summary.py
                 - Minimal code to pass tests
                 → All tests PASS

Step 3 (REFACTOR): Clean up implementation
                 - Extract helpers, improve naming
                 → Tests still PASS
```

### Mock Strategy for External Services

Since we depend on external APIs (LLM, transcription), we use mocks:

```python
# tests/mocks/mock_llm_responses.py
MOCK_PATIENT_SUMMARY = {
    "summary": "58-year-old male with controlled hypertension...",
    "flags": ["Overdue for HbA1c test", "Flu vaccine recommended"],
    "suggested_actions": ["Order lab work", "Schedule follow-up"]
}

# tests/unit/test_patient_summary.py
@pytest.fixture
def mock_llm(mocker):
    provider = mocker.Mock(spec=LLMProvider)
    provider.generate.return_value = json.dumps(MOCK_PATIENT_SUMMARY)
    return provider

async def test_generates_summary_with_conditions(mock_llm, sample_patient):
    result = await generate_patient_summary(sample_patient, mock_llm)
    assert "hypertension" in result.summary.lower()
    assert len(result.flags) > 0
```

### Coverage Requirements

| Area | Minimum Coverage |
|------|------------------|
| Backend services | 80% |
| Backend API routes | 70% |
| Frontend components | 60% |
| Critical paths (LLM, transcription) | 90% |

### Hard Tests: Edge Cases & Failure Scenarios

Tests should cover **realistic failure modes**, not just happy paths:

#### Backend Hard Tests

```python
# Patient Summary Service - Edge Cases
def test_handles_patient_with_no_medical_history():
    """New patient with empty records should still generate useful summary."""

def test_handles_conflicting_medications():
    """Should flag drug interactions in patient's medication list."""

def test_handles_llm_timeout():
    """Should retry and eventually return graceful fallback."""

def test_handles_llm_hallucination_detection():
    """Should validate LLM output against known medical codes."""

# Transcription Service - Edge Cases
def test_handles_poor_audio_quality():
    """Low quality audio should return partial transcript with confidence scores."""

def test_handles_multiple_speakers():
    """Should attempt speaker separation or flag as multi-speaker."""

def test_handles_medical_jargon():
    """Medical terms like 'dyspnea', 'tachycardia' should transcribe correctly."""

def test_handles_accented_speech():
    """Non-native speakers should still transcribe reasonably."""

# Consultation Processor - Edge Cases
def test_handles_incomplete_transcript():
    """Partial transcript should still extract available information."""

def test_handles_off_topic_conversation():
    """Non-medical chatter should be filtered from clinical notes."""

def test_validates_icd_codes_exist():
    """Generated ICD codes must be valid codes from the ICD-10 database."""

def test_flags_potentially_dangerous_prescriptions():
    """Should warn if suggested Rx conflicts with patient allergies."""
```

#### Frontend Hard Tests

```typescript
// AudioRecorder - Edge Cases
test('handles microphone permission denied', async () => {
  // Should show clear error message, not crash
});

test('handles recording interrupted by incoming call', async () => {
  // Should gracefully pause/resume or save partial
});

test('handles very long recordings (30+ minutes)', async () => {
  // Should chunk uploads, show progress
});

test('handles network failure during upload', async () => {
  // Should retry, show offline indicator, queue for later
});

// ConsultationReview - Edge Cases
test('handles extremely long transcript', async () => {
  // Should virtualize list, not freeze UI
});

test('preserves user edits if page accidentally refreshes', async () => {
  // Should auto-save drafts to localStorage
});

test('handles concurrent edits warning', async () => {
  // If opened in multiple tabs, should warn
});
```

#### Integration Hard Tests

```python
# Full Flow Tests
async def test_full_consultation_flow_with_network_failures():
    """
    Simulate: upload succeeds, transcription fails, retry succeeds,
    LLM times out once, succeeds on retry.
    Final result should still be correct.
    """

async def test_handles_malformed_llm_response():
    """
    LLM returns invalid JSON or missing fields.
    Should parse what's available, log error, continue.
    """

async def test_concurrent_consultations():
    """
    Multiple consultations processing simultaneously.
    Should not mix up patient data or transcripts.
    """
```

#### Chaos Testing (Optional for POC)

```python
# Simulated failures
def test_database_connection_lost_mid_request():
def test_external_api_returns_500():
def test_memory_pressure_during_audio_processing():
```

---

## Implementation Phases (TDD)

> **For each feature:** Write tests FIRST → Watch them fail → Implement → Pass → Refactor

### Phase 1: Project Setup

- [ ] Initialize FastAPI backend with project structure
- [ ] Initialize React frontend with Vite + TypeScript
- [ ] **Set up test infrastructure:**
  - [ ] pytest + pytest-asyncio + pytest-mock for backend
  - [ ] Vitest + React Testing Library for frontend
  - [ ] Test database fixtures (SQLite in-memory)
- [ ] Set up SQLite database with patient schema
- [ ] Create sample patient data (5-10 demo patients)
- [ ] Configure environment variables (.env)

### Phase 2: Before Consultation

**Tests First:**

- [ ] `test_patients_api.py` - CRUD endpoint tests
- [ ] `test_patient_summary.py` - Summary generation tests
  - Test: generates summary from patient record
  - Test: extracts conditions and flags correctly
  - Test: handles missing data gracefully
  - Test: returns suggested actions based on patient history
- [ ] `PatientList.test.tsx` - Component renders patient list
- [ ] `PatientSummary.test.tsx` - Component displays AI summary

**Implementation:**

- [ ] **Backend:** Patient CRUD endpoints (`/api/patients`)
- [ ] **Backend:** Patient summary generation service
- [ ] **Frontend:** Patient list view
- [ ] **Frontend:** Patient summary panel (side panel UI)

### Phase 3: During Consultation

**Tests First:**

- [ ] `AudioRecorder.test.tsx` - Audio recorder tests
  - Test: starts recording when button clicked
  - Test: displays timer during recording
  - Test: stops and uploads audio on stop
  - Test: shows error state if mic access denied
- [ ] `test_consultations_api.py` - Upload endpoint tests
  - Test: accepts audio file upload
  - Test: associates consultation with patient
  - Test: rejects invalid file formats

**Implementation:**

- [ ] **Frontend:** Audio recorder component (MediaRecorder API)
- [ ] **Backend:** Audio upload endpoint (`/api/consultations`)
- [ ] **Backend:** Store consultation with patient reference

### Phase 4: After Consultation

**Tests First:**

- [ ] `test_transcription.py` - Transcription service tests
  - Test: transcribes audio file successfully
  - Test: handles API errors gracefully
  - Test: returns timestamps with transcript
- [ ] `test_consultation_processor.py` - AI processing tests
  - Test: generates SOAP notes from transcript
  - Test: extracts ICD-10 codes correctly
  - Test: suggests prescriptions based on context
  - Test: identifies follow-up actions
  - Test: uses patient history for context
- [ ] `ConsultationReview.test.tsx` - Review page tests
  - Test: displays transcript
  - Test: allows editing AI-generated sections
  - Test: saves approved consultation

**Implementation:**

- [ ] **Backend:** Transcription service (Deepgram/AssemblyAI)
- [ ] **Backend:** Consultation processor service
- [ ] **Frontend:** Consultation review page

### Phase 5: LLM Abstraction Layer

**Tests First:**

- [ ] `test_llm_provider.py` - Provider interface tests
  - Test: ClaudeProvider makes correct API call
  - Test: OpenAIProvider makes correct API call
  - Test: handles rate limits and retries
  - Test: config selects correct provider

**Implementation:**

- [ ] Create `LLMProvider` abstract base class
- [ ] Implement `ClaudeProvider`
- [ ] Implement `OpenAIProvider`
- [ ] Config-based provider selection

---

## Data Models

### Patient

```python
class Patient(BaseModel):
    id: str
    name: str
    date_of_birth: date
    conditions: list[str]        # ["Hypertension", "Type 2 Diabetes"]
    medications: list[Medication]
    recent_labs: list[LabResult]
    visit_history: list[Visit]
```

### ConsultationResult

```python
class ConsultationResult(BaseModel):
    transcript: str
    structured_notes: str        # SOAP format
    icd_codes: list[ICDCode]     # [{"code": "R07.9", "description": "Chest pain"}]
    prescriptions: list[Rx]
    follow_up_actions: list[str]
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/patients` | List all patients |
| GET | `/api/patients/{id}` | Get patient details |
| GET | `/api/patients/{id}/summary` | Get AI-generated summary |
| POST | `/api/consultations` | Create consultation (upload audio) |
| GET | `/api/consultations/{id}` | Get consultation details |
| POST | `/api/consultations/{id}/process` | Trigger AI processing |
| PUT | `/api/consultations/{id}` | Update/approve consultation |

---

## Environment Variables

```env
# LLM Configuration
LLM_PROVIDER=claude              # or "openai"
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Transcription
TRANSCRIPTION_PROVIDER=deepgram  # or "assemblyai"
DEEPGRAM_API_KEY=...
ASSEMBLYAI_API_KEY=...

# Database
DATABASE_URL=sqlite:///./data/app.db
```

---

## Key Implementation Files

### Backend Core Services

**`backend/app/services/llm_provider.py`**

```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system: str) -> str:
        """Generate text from the LLM."""
        pass

class ClaudeProvider(LLMProvider):
    async def generate(self, prompt: str, system: str) -> str:
        # Anthropic API call
        ...

class OpenAIProvider(LLMProvider):
    async def generate(self, prompt: str, system: str) -> str:
        # OpenAI API call
        ...
```

**`backend/app/services/patient_summary.py`**

```python
async def generate_patient_summary(patient: Patient, llm: LLMProvider) -> PatientSummary:
    """
    Generate pre-consultation briefing for a patient.
    Returns: summary, conditions, flags, suggested_actions
    """
    ...
```

**`backend/app/services/consultation_processor.py`**

```python
async def process_consultation(
    transcript: str,
    patient: Patient,
    llm: LLMProvider
) -> ConsultationResult:
    """
    Process transcript into structured clinical output.
    Returns: notes (SOAP format), icd_codes, prescriptions, follow_up_actions
    """
    ...
```

### Frontend Core Components

**`frontend/src/components/AudioRecorder.tsx`**

- MediaRecorder API integration
- Visual feedback (recording state, timer, audio levels)
- Upload to backend on stop

**`frontend/src/pages/AfterConsultation.tsx`**

- Display transcript with timestamps
- Editable AI-generated sections
- Save/approve actions

---

## Verification Plan

### Manual Testing

1. **Before phase:** Select patient → verify AI summary appears with conditions, flags
2. **During phase:** Record 1-2 min audio → verify upload succeeds
3. **After phase:** Trigger processing → verify transcript + AI analysis generated

### Automated Tests

- Unit tests for LLM provider abstraction
- Integration tests for transcription service
- API endpoint tests with pytest

### Demo Scenario

Use this test case:

- **Patient:** "John Davis, 58, Hypertension, Type 2 Diabetes"
- **Simulated consultation:** Chest pain discussion
- **Expected output:** ICD-10 R07.9, ECG prescription, follow-up in 2 weeks

---

## Deliverables

1. Working backend API with all endpoints
2. React UI with 3 screens (Before/During/After)
3. LLM integration (Claude + OpenAI support)
4. Transcription integration (Deepgram or AssemblyAI)
5. Sample patient data for demos
6. README with setup instructions

---

## Open Questions / Future Considerations

- [ ] Speaker diarization (distinguishing doctor vs patient voice)
- [ ] Medical terminology accuracy in transcription
- [ ] HIPAA/HDS compliance for production
- [ ] Multi-language support (French/English)
