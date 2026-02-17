---
name: staff-architect
description: Architecture guidance for AI Doctor Assistant
---

# Staff Architect Skill

## Core Architecture: Rules → Agent Pattern

```
┌─────────────────────────────────────────────────┐
│              Two-Step Briefing Flow             │
├─────────────────────────────────────────────────┤
│                                                 │
│  STEP 1: Deterministic Rules (Python)           │
│  - FlagAnalyzer.apply_rules(patient)            │
│  - Returns: List[Flag] (100% deterministic)     │
│  - Source: "rule"                               │
│                                                 │
│  STEP 2: AI Synthesis (Claude Agent SDK)        │
│  - BriefingAgent.generate(patient, rule_flags)  │
│  - Returns: PatientBriefing (Pydantic validated)│
│  - AI insights: source="ai"                     │
│                                                 │
└─────────────────────────────────────────────────┘
```

## Why This Pattern?

| Benefit | Explanation |
|---------|-------------|
| Auditability | Can prove which flags came from rules vs AI |
| Testability | Unit test rules separately, mock agent for integration |
| Reliability | Rules are 100% deterministic (critical for healthcare) |
| Traceability | Clear separation: `source: "rule"` vs `source: "ai"` |

## Data Flow

```
Frontend → API → Service → Agent → Tools
                              ↓
                         Rule Engine
```

## API Design

- Version all APIs: `/api/v1/...`
- Structured error responses with codes
- Document decisions in ADRs

## Key Principles

1. **Keep services loosely coupled**
   - Each service has single responsibility
   - Communicate via well-defined interfaces

2. **Prefer explicit over implicit**
   - No magic, clear data flow
   - Type hints everywhere

3. **Don't over-engineer**
   - Build for today, not hypothetical futures
   - Simple > clever

4. **Healthcare Context**
   - Auditability is non-negotiable
   - Log all AI decisions with reasoning
   - Never log patient PII to console
   - Tag all flags with their source

## When to Create New Services

- When a module exceeds ~200 lines
- When logic is reused across multiple routers
- When you need to test complex business logic in isolation

## When NOT to Abstract

- One-off operations
- Simple CRUD
- Configuration code
