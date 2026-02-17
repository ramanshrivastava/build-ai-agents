# AI Doctor Assistant - POC Plan (Iteration 2)

> Created: February 4, 2026
> Status: Draft for approval

## Focus: Pre-Consultation Patient Briefing

> **"2-minute read before entering the room"**
> Doctors love starting informed.

---

## What This POC Delivers

A focused tool that shows doctors everything they need to know about a patient **before** the consultation begins:

| Feature | Description |
|---------|-------------|
| **Patient Summary** | Concise overview of history, conditions, treatments |
| **Smart Flags** | Missing follow-ups, overdue exams, risks |
| **Suggested Actions** | What the doctor might want to address today |
| **Priority Ranking** | Most critical info surfaced first |

---

## Why Focus on "Before"?

This is the **highest-value, lowest-complexity** starting point:

1. **No audio/transcription needed** - simpler tech stack
2. **Immediate value** - doctors can use it from day one
3. **Measurable impact** - did the doctor feel more prepared?
4. **Foundation for later** - the patient context feeds into "During" and "After" phases

---

## User Flow

```
Doctor's Day:
┌─────────────────────────────────────────────────────────────┐
│  9:00 AM - First patient: Jean Dupont                       │
│                                                             │
│  Doctor opens AI Assistant:                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  🔴 ALERT: HbA1c overdue (last: 6 months ago)       │   │
│  │  🟡 REMINDER: Flu vaccine recommended (age 65+)     │   │
│  │                                                     │   │
│  │  SUMMARY                                            │   │
│  │  Jean Dupont, 67M                                   │   │
│  │  • Type 2 Diabetes (10 years) - well controlled     │   │
│  │  • Hypertension - on Lisinopril 10mg                │   │
│  │  • Last visit: chest pain workup (ECG normal)       │   │
│  │                                                     │   │
│  │  CURRENT MEDICATIONS                                │   │
│  │  • Metformin 500mg BID                              │   │
│  │  • Lisinopril 10mg QD                               │   │
│  │  • Aspirin 81mg QD                                  │   │
│  │                                                     │   │
│  │  SUGGESTED ACTIONS                                  │   │
│  │  □ Order HbA1c                                      │   │
│  │  □ Discuss flu vaccination                          │   │
│  │  □ Follow up on chest pain - any recurrence?       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Doctor reads in 2 minutes → enters room fully prepared     │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture (Claude Agent SDK)

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React)                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────────────────────────────┐  │
│  │ Patient     │  │        Patient Briefing              │  │
│  │ List        │  │  • Alerts/Flags                      │  │
│  │             │  │  • Summary                           │  │
│  │ Search      │  │  • Medications                       │  │
│  │ Filter      │  │  • Recent visits                     │  │
│  │             │  │  • Suggested actions                 │  │
│  └─────────────┘  └─────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │ REST API
┌────────────────────────────┴────────────────────────────────┐
│                    Backend (FastAPI)                         │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Claude Agent SDK                          │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  BriefingAgent                                  │  │  │
│  │  │  • Tools: fetch_patient, analyze_flags,         │  │  │
│  │  │           check_drug_interactions,              │  │  │
│  │  │           validate_icd_codes                    │  │  │
│  │  │  • Hooks: observability, audit logging          │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  Services:                                                   │
│  • PatientService       - CRUD operations                    │
│  • FlagAnalyzer         - Rule-based flag detection          │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────┐
│  Claude API  │  SQLite  │  Langfuse (Observability)         │
└──────────────┴──────────┴───────────────────────────────────┘
```

---

## Claude Agent SDK Integration

### Why Agent SDK?

The Claude Agent SDK provides:
- **Tool use** - Agent can call functions (fetch patient, check interactions)
- **Hooks** - Built-in observability at every step
- **Structured output** - Reliable JSON responses
- **Error handling** - Retries, timeouts, fallbacks built-in

### BriefingAgent Design

```python
from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher

# Define tools the agent can use
BRIEFING_TOOLS = [
    {
        "name": "fetch_patient",
        "description": "Fetch patient record from database",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"}
            },
            "required": ["patient_id"]
        }
    },
    {
        "name": "check_drug_interactions",
        "description": "Check for interactions between medications",
        "input_schema": {
            "type": "object",
            "properties": {
                "medications": {"type": "array", "items": {"type": "string"}}
            }
        }
    },
    {
        "name": "validate_icd_code",
        "description": "Validate an ICD-10 code exists",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"}
            }
        }
    },
    {
        "name": "get_monitoring_rules",
        "description": "Get required monitoring for a condition",
        "input_schema": {
            "type": "object",
            "properties": {
                "condition": {"type": "string"}
            }
        }
    }
]

# Tool implementations
async def handle_tool_call(tool_name: str, tool_input: dict) -> str:
    if tool_name == "fetch_patient":
        patient = await patient_service.get(tool_input["patient_id"])
        return patient.model_dump_json()
    elif tool_name == "check_drug_interactions":
        interactions = await drug_db.check_interactions(tool_input["medications"])
        return json.dumps(interactions)
    elif tool_name == "validate_icd_code":
        is_valid = icd_db.validate(tool_input["code"])
        return json.dumps({"valid": is_valid})
    elif tool_name == "get_monitoring_rules":
        rules = MONITORING_RULES.get(tool_input["condition"], {})
        return json.dumps(rules)

# Generate briefing using agent
async def generate_briefing(patient_id: str) -> PatientBriefing:
    async for message in query(
        prompt=f"""
        Generate a pre-consultation briefing for patient {patient_id}.

        Steps:
        1. Fetch the patient record
        2. Check for drug interactions in their medications
        3. Get monitoring rules for each condition
        4. Identify overdue labs/vaccines based on rules
        5. Generate a concise briefing

        Return a JSON briefing with: flags, summary, medications, recent_visits, suggested_actions
        """,
        options=ClaudeAgentOptions(
            tools=BRIEFING_TOOLS,
            hooks=OBSERVABILITY_HOOKS,
            max_tokens=4096
        )
    ):
        if hasattr(message, "result"):
            return PatientBriefing.model_validate_json(message.result)
```

### Agent Hooks for Observability

```python
from claude_agent_sdk import HookCallback
import langfuse

# Initialize Langfuse client
langfuse_client = langfuse.Langfuse()

async def trace_tool_calls(input_data, tool_use_id, context):
    """Log every tool call to Langfuse"""
    if input_data['hook_event_name'] == 'PreToolUse':
        langfuse_client.trace(
            name=f"tool:{input_data['tool_name']}",
            input=input_data['tool_input'],
            metadata={"tool_use_id": tool_use_id}
        )
    elif input_data['hook_event_name'] == 'PostToolUse':
        langfuse_client.trace(
            name=f"tool:{input_data['tool_name']}:result",
            output=input_data.get('tool_result'),
            metadata={"tool_use_id": tool_use_id}
        )
    return {}

async def audit_logger(input_data, tool_use_id, context):
    """Log to audit file for compliance"""
    with open('./audit.log', 'a') as f:
        f.write(f"{datetime.now().isoformat()}: {input_data['hook_event_name']} - {input_data.get('tool_name', 'N/A')}\n")
    return {}

OBSERVABILITY_HOOKS = {
    "PreToolUse": [HookMatcher(hooks=[trace_tool_calls, audit_logger])],
    "PostToolUse": [HookMatcher(hooks=[trace_tool_calls])],
}
```

---

## Observability Strategy

### Recommended: Langfuse (Open Source)

Why Langfuse:
- **Open source** - can self-host for HIPAA compliance
- **Free tier** - generous for POC
- **Native Claude Agent SDK support** - via OpenTelemetry
- **Rich UI** - trace viewer, cost tracking, latency analysis

### Setup

```python
# backend/app/observability.py
import langfuse
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from langfuse.opentelemetry import LangfuseSpanProcessor

def setup_observability():
    # Initialize Langfuse
    langfuse_processor = LangfuseSpanProcessor(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    )

    # Set up OpenTelemetry
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(langfuse_processor))
    trace.set_tracer_provider(provider)
```

### What We Track

| Metric | Purpose |
|--------|---------|
| **Latency** | Briefing generation time |
| **Token usage** | Cost per briefing |
| **Tool calls** | Which tools used, success/failure |
| **Errors** | Failed generations, timeouts |
| **Traces** | Full conversation flow |

### Alternative: LangSmith

If you prefer LangChain ecosystem:
```python
from langsmith import Client
client = Client()  # Auto-configures from LANGCHAIN_API_KEY
```

---

## PDF Handling (Future Phase)

### PDF Types and Extraction Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    PDF Processing Pipeline                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  PDF Input                                                   │
│      │                                                       │
│      ▼                                                       │
│  ┌─────────────┐                                            │
│  │ PDF Type    │                                            │
│  │ Detection   │                                            │
│  └──────┬──────┘                                            │
│         │                                                    │
│    ┌────┴────┬────────────┐                                 │
│    ▼         ▼            ▼                                 │
│ Digital   Scanned     Form-based                            │
│    │         │            │                                 │
│    ▼         ▼            ▼                                 │
│ PyMuPDF   Tesseract   PyMuPDF                              │
│ pdfplumber  + OCR     form fields                          │
│    │         │            │                                 │
│    └────┬────┴────────────┘                                 │
│         ▼                                                    │
│  ┌─────────────┐                                            │
│  │ Raw Text    │                                            │
│  └──────┬──────┘                                            │
│         ▼                                                    │
│  ┌─────────────┐                                            │
│  │ Claude Agent│  ← Extract structured data                 │
│  │ + Tools     │    (conditions, meds, labs)                │
│  └──────┬──────┘                                            │
│         ▼                                                    │
│  ┌─────────────┐                                            │
│  │ Structured  │  → Patient model                           │
│  │ Patient Data│                                            │
│  └─────────────┘                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### PDF Extraction Tools for Agent

```python
PDF_EXTRACTION_TOOLS = [
    {
        "name": "read_pdf",
        "description": "Extract text from a PDF file",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "pages": {"type": "array", "items": {"type": "integer"}}
            }
        }
    },
    {
        "name": "extract_table",
        "description": "Extract a table from PDF (e.g., lab results)",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "page": {"type": "integer"},
                "table_description": {"type": "string"}
            }
        }
    }
]
```

### POC Recommendation

**For POC: Start with structured JSON data**
- Faster to build
- Easier to test
- Focus on the AI briefing logic

**Add PDF extraction in Phase 2:**
- Once briefing logic is proven
- When you have real PDF samples to test with
- May need OCR depending on PDF quality

---

## Deep Dive: Patient Data Model

### Core Patient Record

```python
class Patient(BaseModel):
    id: str
    # Demographics
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str                      # M/F/Other

    # Medical History
    conditions: list[Condition]       # Active conditions
    past_conditions: list[Condition]  # Resolved conditions
    allergies: list[Allergy]

    # Current Treatment
    medications: list[Medication]

    # Monitoring
    lab_results: list[LabResult]
    vital_signs: list[VitalSign]

    # Visit History
    visits: list[Visit]

    # Preventive Care
    vaccinations: list[Vaccination]
    screenings: list[Screening]

    # Social/Lifestyle (optional but valuable)
    smoking_status: str | None
    alcohol_use: str | None
    occupation: str | None


class Condition(BaseModel):
    name: str                        # "Type 2 Diabetes"
    icd_code: str | None             # "E11.9"
    onset_date: date | None
    status: str                      # "active", "controlled", "resolved"
    severity: str | None             # "mild", "moderate", "severe"
    notes: str | None


class Medication(BaseModel):
    name: str                        # "Metformin"
    dosage: str                      # "500mg"
    frequency: str                   # "BID" (twice daily)
    start_date: date | None
    prescribing_reason: str | None   # Links to condition
    refills_remaining: int | None


class LabResult(BaseModel):
    test_name: str                   # "HbA1c"
    value: str                       # "6.8"
    unit: str                        # "%"
    date: date
    reference_range: str | None      # "4.0-5.6"
    is_abnormal: bool


class Visit(BaseModel):
    date: date
    reason: str                      # "Chest pain evaluation"
    summary: str                     # Brief note of what happened
    diagnoses: list[str]             # ICD codes or descriptions
    prescriptions_issued: list[str]
    follow_up_instructions: str | None
```

---

## Deep Dive: Flagging System

The flag analyzer combines **rule-based logic** (deterministic) with **AI analysis** (contextual):

### Flag Categories

```python
class Flag(BaseModel):
    category: FlagCategory
    severity: FlagSeverity           # critical, warning, info
    title: str                       # "HbA1c overdue"
    description: str                 # "Last HbA1c was 6 months ago..."
    suggested_action: str | None     # "Order HbA1c test"
    related_condition: str | None    # "Type 2 Diabetes"


class FlagCategory(Enum):
    OVERDUE_LAB = "overdue_lab"           # Lab test past due date
    OVERDUE_SCREENING = "overdue_screening"  # Cancer screening, etc.
    MISSING_VACCINATION = "missing_vaccination"
    DRUG_INTERACTION = "drug_interaction"
    ABNORMAL_TREND = "abnormal_trend"     # Lab values trending wrong way
    FOLLOW_UP_DUE = "follow_up_due"       # Scheduled follow-up overdue
    HIGH_RISK = "high_risk"               # Risk factors requiring attention
    LIFESTYLE = "lifestyle"               # Smoking, etc.


class FlagSeverity(Enum):
    CRITICAL = "critical"   # 🔴 Must address
    WARNING = "warning"     # 🟡 Should address
    INFO = "info"           # 🔵 Good to know
```

### Rule-Based Flags (Deterministic)

```python
# backend/app/services/flag_rules.py

MONITORING_RULES = {
    "Type 2 Diabetes": {
        "HbA1c": {"frequency_months": 3, "severity": "critical"},
        "Lipid Panel": {"frequency_months": 12, "severity": "warning"},
        "Kidney Function": {"frequency_months": 12, "severity": "warning"},
        "Eye Exam": {"frequency_months": 12, "severity": "warning"},
        "Foot Exam": {"frequency_months": 12, "severity": "info"},
    },
    "Hypertension": {
        "Blood Pressure": {"frequency_months": 3, "severity": "warning"},
        "Kidney Function": {"frequency_months": 12, "severity": "warning"},
    },
}

VACCINATION_RULES = {
    "Flu": {"min_age": 65, "frequency_months": 12},
    "Pneumonia": {"min_age": 65, "one_time": True},
    "Shingles": {"min_age": 50, "one_time": True},
}

SCREENING_RULES = {
    "Colonoscopy": {"min_age": 45, "max_age": 75, "frequency_years": 10},
    "Mammogram": {"gender": "F", "min_age": 40, "frequency_years": 2},
}
```

### AI-Enhanced Flags (via Agent)

The BriefingAgent handles complex pattern detection as part of briefing generation:

```python
# The agent prompt includes pattern detection instructions
BRIEFING_AGENT_PROMPT = """
Generate a pre-consultation briefing for patient {patient_id}.

Steps:
1. Fetch the patient record using fetch_patient tool
2. Check for drug interactions using check_drug_interactions tool
3. Get monitoring rules for each condition
4. Identify overdue labs/vaccines based on rules
5. **Analyze for subtle patterns:**
   - Symptoms across visits suggesting missed diagnosis
   - Lab trends indicating worsening condition
   - Medication non-adherence signals
   - Social/lifestyle factors affecting outcomes
6. Generate the briefing with all flags (rule-based + AI-detected)

Return JSON with: flags, summary, medications, recent_visits, suggested_actions
"""

# AI-detected flags are merged with rule-based flags
# Agent can use tools to validate its findings
```

---

## Deep Dive: AI Summary Generation

### Summary Structure

```python
class PatientBriefing(BaseModel):
    # Priority alerts (shown first, prominently)
    flags: list[Flag]

    # Quick overview (the "2-minute read")
    summary: BriefingSummary

    # Current medications (always relevant)
    medications: list[MedicationDisplay]

    # Recent context
    recent_visits: list[VisitSummary]  # Last 3 visits

    # What to consider today
    suggested_actions: list[SuggestedAction]


class BriefingSummary(BaseModel):
    one_liner: str              # "67M, T2DM (controlled), HTN, recent chest pain workup"
    key_conditions: list[str]   # Active conditions with status
    relevant_history: str       # 2-3 sentences of relevant context


class SuggestedAction(BaseModel):
    action: str                 # "Order HbA1c"
    reason: str                 # "Overdue by 3 months per diabetes protocol"
    priority: int               # 1 = highest
    can_order_now: bool         # For future: quick action buttons
```

### LLM Prompt Strategy

```python
BRIEFING_SYSTEM_PROMPT = """
You are a clinical assistant helping doctors prepare for patient consultations.
Your job is to create a concise, actionable briefing that a doctor can read in 2 minutes.

Guidelines:
- Be concise but complete
- Surface the most important information first
- Flag anything unusual or concerning
- Connect dots the doctor might miss (e.g., "patient complained of fatigue in last 3 visits - consider thyroid screening")
- Use standard medical abbreviations
- Don't repeat obvious information
- Focus on actionable insights

Output format: JSON matching the BriefingSummary schema
"""

BRIEFING_USER_PROMPT = """
Generate a pre-consultation briefing for this patient.

Patient Record:
{patient_json}

Today's scheduled appointment reason (if known): {appointment_reason}

Create a briefing that helps the doctor:
1. Quickly understand who this patient is (one-liner summary)
2. Know the key active conditions and their status
3. Understand recent context (what happened in last few visits)
4. Be aware of anything they should address today
"""
```

---

## Project Structure

```
ai-doctor-assistant/
├── docs/
│   ├── RAW-PRD.md
│   ├── PLAN-ITERATION-1.md
│   ├── PLAN-ITERATION-2.md          # This plan
│   └── ...
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models/
│   │   │   ├── patient.py           # Full patient data model
│   │   │   ├── flag.py              # Flag/alert models
│   │   │   └── briefing.py          # Briefing output models
│   │   ├── agents/
│   │   │   ├── briefing_agent.py    # Claude Agent SDK briefing agent
│   │   │   ├── tools.py             # Agent tool definitions
│   │   │   └── hooks.py             # Observability hooks
│   │   ├── services/
│   │   │   ├── patient_service.py   # Patient CRUD
│   │   │   ├── flag_analyzer.py     # Rule-based flag detection
│   │   │   └── drug_interactions.py # Drug interaction checker
│   │   ├── observability/
│   │   │   ├── langfuse_setup.py    # Langfuse/OTEL configuration
│   │   │   └── audit_logger.py      # Audit trail for compliance
│   │   ├── routers/
│   │   │   ├── patients.py
│   │   │   └── briefings.py
│   │   └── database.py
│   ├── data/
│   │   ├── sample_patients.json     # Rich demo patients
│   │   ├── flag_rules.json          # Configurable rules
│   │   ├── drug_interactions.json   # Known drug interactions
│   │   └── icd_codes.json           # For validation
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── unit/
│   │   │   ├── test_flag_analyzer.py
│   │   │   ├── test_briefing_agent.py
│   │   │   └── test_agent_tools.py
│   │   └── integration/
│   │       └── test_briefing_api.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── PatientList/
│   │   │   │   ├── PatientList.tsx
│   │   │   │   ├── PatientList.test.tsx
│   │   │   │   ├── PatientSearch.tsx
│   │   │   │   └── PatientCard.tsx
│   │   │   ├── Briefing/
│   │   │   │   ├── BriefingPanel.tsx
│   │   │   │   ├── BriefingPanel.test.tsx
│   │   │   │   ├── FlagList.tsx
│   │   │   │   ├── SummarySection.tsx
│   │   │   │   ├── MedicationList.tsx
│   │   │   │   ├── RecentVisits.tsx
│   │   │   │   └── SuggestedActions.tsx
│   │   │   └── common/
│   │   │       ├── LoadingSpinner.tsx
│   │   │       └── ErrorBoundary.tsx
│   │   ├── pages/
│   │   │   └── Dashboard.tsx        # Main page: list + briefing
│   │   ├── services/
│   │   │   └── api.ts
│   │   ├── hooks/
│   │   │   ├── usePatients.ts
│   │   │   └── useBriefing.ts
│   │   └── App.tsx
│   └── ...
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/patients` | List patients (with search/filter) |
| GET | `/api/patients/{id}` | Get full patient record |
| GET | `/api/patients/{id}/briefing` | Get AI-generated briefing |
| POST | `/api/patients/{id}/briefing/refresh` | Force regenerate briefing |

### Briefing Response Example

```json
{
  "patient_id": "p123",
  "generated_at": "2026-02-04T10:30:00Z",
  "flags": [
    {
      "category": "overdue_lab",
      "severity": "critical",
      "title": "HbA1c overdue",
      "description": "Last HbA1c (6.8%) was 6 months ago. Per diabetes protocol, should be every 3 months.",
      "suggested_action": "Order HbA1c",
      "related_condition": "Type 2 Diabetes"
    },
    {
      "category": "missing_vaccination",
      "severity": "warning",
      "title": "Flu vaccine recommended",
      "description": "Patient is 67 years old, no flu vaccine recorded this season.",
      "suggested_action": "Offer flu vaccination"
    }
  ],
  "summary": {
    "one_liner": "67M, T2DM (controlled), HTN, s/p chest pain workup",
    "key_conditions": [
      "Type 2 Diabetes - controlled on Metformin, last HbA1c 6.8%",
      "Hypertension - stable on Lisinopril 10mg",
      "Recent chest pain (Dec 2025) - evaluated, ECG normal, likely musculoskeletal"
    ],
    "relevant_history": "Diabetic for 10 years with good control. Hypertension well-managed. Presented with chest pain in December, workup negative. Works as accountant, sedentary. Former smoker (quit 5 years ago)."
  },
  "medications": [
    {"name": "Metformin", "dosage": "500mg BID", "for": "Type 2 Diabetes"},
    {"name": "Lisinopril", "dosage": "10mg QD", "for": "Hypertension"},
    {"name": "Aspirin", "dosage": "81mg QD", "for": "Cardioprotection"}
  ],
  "recent_visits": [
    {
      "date": "2025-12-15",
      "reason": "Chest pain",
      "summary": "Presented with intermittent chest pain x 1 week. ECG normal, troponin negative. Likely musculoskeletal. Advised NSAIDs PRN, follow up if worsens."
    },
    {
      "date": "2025-09-10",
      "reason": "Diabetes follow-up",
      "summary": "HbA1c 6.8% (improved from 7.2%). Continued Metformin. Reinforced diet/exercise."
    }
  ],
  "suggested_actions": [
    {"action": "Order HbA1c", "reason": "Overdue per protocol", "priority": 1},
    {"action": "Discuss flu vaccination", "reason": "Age 65+, not vaccinated this season", "priority": 2},
    {"action": "Ask about chest pain", "reason": "Follow up from December visit", "priority": 3}
  ]
}
```

---

## Implementation Phases (TDD)

### Phase 1: Foundation Setup
- [ ] Initialize project structure (FastAPI + React)
- [ ] Set up test infrastructure (pytest, Vitest)
- [ ] Create patient data models
- [ ] Create flag/briefing models
- [ ] Set up SQLite database
- [ ] Create sample patients (5 rich examples)

### Phase 2: Flag Analyzer (Rule-Based)
**Tests first:**
```python
def test_flags_overdue_hba1c_for_diabetic():
    """Diabetic patient with HbA1c older than 3 months → critical flag"""

def test_no_flag_if_hba1c_recent():
    """Diabetic patient with recent HbA1c → no overdue flag"""

def test_flags_missing_flu_vaccine_over_65():
    """Patient 65+ without flu vaccine this season → warning flag"""

def test_flags_drug_interaction():
    """Patient on conflicting medications → critical flag"""

def test_multiple_flags_sorted_by_severity():
    """Multiple flags returned in severity order (critical first)"""
```

**Implementation:**
- [ ] FlagAnalyzer service with rule engine
- [ ] Configurable rules (JSON file)
- [ ] Flag priority sorting

### Phase 3: Claude Agent SDK Integration
**Tests first:**
```python
def test_agent_tool_fetch_patient():
    """fetch_patient tool returns correct patient data"""

def test_agent_tool_check_drug_interactions():
    """check_drug_interactions identifies known conflicts"""

def test_agent_tool_validate_icd_code():
    """validate_icd_code returns true for valid codes"""

def test_agent_handles_tool_error():
    """Agent gracefully handles tool failures"""

def test_observability_hooks_fire():
    """Hooks log tool calls to Langfuse"""
```

**Implementation:**
- [ ] Define agent tools (fetch_patient, check_interactions, etc.)
- [ ] Implement tool handlers
- [ ] Set up observability hooks (Langfuse integration)
- [ ] Configure agent options (retries, timeouts)

### Phase 4: Briefing Agent
**Tests first:**
```python
def test_briefing_agent_generates_valid_output():
    """Agent returns properly structured PatientBriefing"""

def test_briefing_agent_uses_patient_tool():
    """Agent calls fetch_patient tool"""

def test_briefing_agent_checks_interactions():
    """Agent calls check_drug_interactions when meds present"""

def test_briefing_includes_flags_from_rules():
    """Briefing includes flags from rule-based analyzer"""

def test_briefing_handles_minimal_patient_data():
    """New patient with sparse data still gets useful briefing"""

def test_agent_traces_logged_to_langfuse():
    """Full agent trace appears in Langfuse"""
```

**Implementation:**
- [ ] BriefingAgent with prompt and tools
- [ ] Response parsing and validation
- [ ] Integrate with FlagAnalyzer for rule-based flags
- [ ] Caching strategy (briefings don't change quickly)
- [ ] Langfuse trace visualization

### Phase 5: Frontend - Patient List
**Tests first:**
```typescript
test('displays list of patients', () => {})
test('filters patients by search term', () => {})
test('shows loading state while fetching', () => {})
test('shows error state on API failure', () => {})
test('selects patient and loads briefing', () => {})
```

**Implementation:**
- [ ] PatientList component
- [ ] PatientSearch component
- [ ] PatientCard component
- [ ] usePatients hook

### Phase 6: Frontend - Briefing Panel
**Tests first:**
```typescript
test('displays flags sorted by severity', () => {})
test('shows critical flags with red indicator', () => {})
test('displays patient summary one-liner', () => {})
test('lists current medications', () => {})
test('shows suggested actions with checkboxes', () => {})
test('handles loading state', () => {})
test('handles briefing generation error', () => {})
```

**Implementation:**
- [ ] BriefingPanel component
- [ ] FlagList component
- [ ] SummarySection component
- [ ] MedicationList component
- [ ] SuggestedActions component
- [ ] useBriefing hook

### Phase 7: Integration & Polish
- [ ] Connect frontend to backend
- [ ] Error handling throughout
- [ ] Loading states
- [ ] Responsive design
- [ ] End-to-end manual testing

---

## Hard Tests

### Flag Analyzer Edge Cases
```python
def test_handles_patient_with_no_conditions():
    """Patient with no diagnoses should check general screening rules"""

def test_handles_conflicting_data():
    """Lab date in future, missing fields, etc."""

def test_handles_rare_conditions():
    """Conditions not in our rule set should not crash"""

def test_medication_interaction_with_allergies():
    """Patient allergic to penicillin prescribed amoxicillin → critical flag"""
```

### Agent Edge Cases
```python
def test_agent_handles_tool_timeout():
    """Agent retries and eventually returns partial briefing"""

def test_agent_handles_invalid_patient_id():
    """Agent returns clear error message"""

def test_agent_handles_api_rate_limit():
    """Agent implements backoff and retries"""

def test_agent_output_validated_against_schema():
    """Invalid JSON from agent raises proper error"""

def test_agent_doesnt_hallucinate_medications():
    """Medications in briefing exist in patient record"""

def test_agent_handles_very_long_patient_history():
    """Patient with 50+ visits doesn't exceed context window"""

def test_agent_handles_non_english_content():
    """French condition names work correctly"""
```

### Observability Edge Cases
```python
def test_langfuse_trace_includes_all_tool_calls():
    """Every tool call appears in trace"""

def test_langfuse_handles_connection_failure():
    """Briefing still works if Langfuse is down"""

def test_audit_log_captures_patient_access():
    """All patient data access is logged"""
```

### Frontend Edge Cases
```typescript
test('handles extremely long flag descriptions', () => {})
test('handles patient with 20+ medications', () => {})
test('handles rapid patient selection changes', () => {})
test('preserves scroll position in briefing panel', () => {})
test('shows loading state during agent processing', () => {})
```

---

## Sample Patient Data

Create 5 rich patient profiles for testing:

| Patient | Profile | Testing Purpose |
|---------|---------|-----------------|
| Jean Dupont | 67M, T2DM + HTN, multiple overdue items | Tests multiple flags |
| Marie Laurent | 45F, healthy, routine visit | Tests minimal flags |
| Pierre Martin | 72M, complex cardiac history | Tests prioritization |
| Sophie Bernard | 35F, new patient, sparse data | Tests handling minimal data |
| Ahmed Hassan | 58M, diabetes with poor control | Tests trend detection |

---

## Environment Variables

```env
# Claude Agent SDK
ANTHROPIC_API_KEY=sk-ant-...

# Observability (Langfuse)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com  # or self-hosted URL

# Database
DATABASE_URL=sqlite:///./data/app.db

# Briefing cache (optional)
BRIEFING_CACHE_TTL_MINUTES=60

# Feature flags
ENABLE_DRUG_INTERACTION_CHECK=true
ENABLE_AI_PATTERN_DETECTION=true
```

### Key Dependencies (requirements.txt)

```txt
# Backend Framework
fastapi>=0.109.0
uvicorn>=0.27.0
pydantic>=2.5.0

# Claude Agent SDK
claude-agent-sdk>=0.1.0

# Observability
langfuse>=2.0.0
opentelemetry-api>=1.22.0
opentelemetry-sdk>=1.22.0

# Database
sqlalchemy>=2.0.0
aiosqlite>=0.19.0

# Testing
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-mock>=3.12.0
httpx>=0.26.0

# PDF Processing (Future)
# pymupdf>=1.23.0
# pytesseract>=0.3.10
```

---

## Verification Plan

### Manual Testing Checklist
1. [ ] Open app → patient list loads
2. [ ] Search for patient → results filter correctly
3. [ ] Select patient → briefing panel shows loading
4. [ ] Briefing loads → flags appear in severity order
5. [ ] Critical flags have red indicator
6. [ ] Summary one-liner matches patient
7. [ ] Medications list is accurate
8. [ ] Suggested actions are relevant
9. [ ] Select different patient → briefing updates

### Demo Scenario
**Patient:** Jean Dupont, 67M, Type 2 Diabetes + Hypertension

**Expected Briefing:**
- 🔴 Flag: HbA1c overdue (critical)
- 🟡 Flag: Flu vaccine recommended (warning)
- Summary: "67M, T2DM (controlled), HTN, s/p chest pain workup"
- 3 medications listed
- 2-3 recent visits shown
- Actions: Order HbA1c, Discuss flu vaccine, Follow up on chest pain

---

## Success Criteria

This POC is successful if:
1. **Functional:** Doctor can select patient and see AI-generated briefing
2. **Accurate:** Flags correctly identify overdue items and risks
3. **Fast:** Briefing loads within 3-5 seconds
4. **Useful:** "2-minute read" provides actionable information
5. **Testable:** 80%+ test coverage on backend services

---

## Next Steps After POC

If this proves valuable:
1. Add briefing caching for performance
2. Add "During" phase (audio recording)
3. Add "After" phase (transcription + analysis)
4. Connect to real patient data sources
5. Deploy as Electron app for overlay capability
