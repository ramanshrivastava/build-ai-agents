"""Briefing generation service — delegates to RAG agent with V1 fallback."""

from __future__ import annotations

import datetime
import json
import logging

from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    ClaudeAgentOptions,
    ProcessError,
    ResultMessage,
    query,
)

from src.config import settings
from src.models.orm import Patient
from src.models.schemas import BriefingResponse, PatientBriefing

logger = logging.getLogger(__name__)

# V1 system prompt (fallback when Qdrant is unavailable)
V1_SYSTEM_PROMPT = """\
You are a clinical decision support assistant preparing pre-consultation \
briefings for physicians. Your role is to analyze a patient record and \
produce a structured briefing that helps the doctor prepare for the visit.

INPUT: You will receive a patient record in JSON format containing demographics, \
conditions, medications, lab results (with reference ranges), allergies, and visits.

OUTPUT: Produce a structured briefing with flags, summary, and suggested actions.

FLAG GUIDELINES:
- category "labs": Flag lab values outside reference ranges.
- category "medications": Flag medication concerns (high doses, combinations, adherence).
- category "screenings": Flag overdue preventive screenings based on age/gender/conditions.
- category "ai_insight": Flag clinical patterns you notice across the data.
- severity "critical": Immediate clinical concern (e.g., dangerously abnormal lab, \
  dangerous drug interaction, acute risk).
- severity "warning": Needs attention this visit (e.g., moderately abnormal lab, \
  overdue screening, suboptimal control).
- severity "info": Worth noting but not urgent (e.g., mildly abnormal value trending \
  in right direction, general health maintenance).
- source is always "ai".
- Include suggested_action when a concrete next step exists.

SUMMARY GUIDELINES:
- one_liner: Single sentence capturing the patient's clinical picture and visit context.
- key_conditions: List active conditions from the record.
- relevant_history: Brief paragraph of clinically relevant context for this visit.

SUGGESTED ACTIONS (3-5):
- Prioritize by clinical urgency (priority 1 = most urgent).
- Each action should be specific and actionable for this visit.
- Include a brief reason explaining why.

CONSTRAINTS:
- Only flag issues visible in the provided data. Do not fabricate information.
- If the patient has no concerning findings, produce fewer/no flags and say so in the summary.
- Be concise. Physicians need quick, scannable information.
"""


class BriefingGenerationError(Exception):
    """Raised when briefing generation fails."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _qdrant_available() -> bool:
    """Check if Qdrant is reachable. Returns False on any error."""
    try:
        from src.services.rag_service import get_qdrant_client

        client = get_qdrant_client()
        collections = client.get_collections()
        names = [c.name for c in collections.collections]
        logger.debug("Qdrant health check OK, collections: %s", names)
        return True
    except Exception as e:
        logger.debug("Qdrant health check failed: %s", e)
        return False


def _serialize_patient(patient: Patient) -> str:
    """Convert Patient ORM object to JSON string for the agent."""
    data = {
        "name": patient.name,
        "date_of_birth": patient.date_of_birth.isoformat(),
        "gender": patient.gender,
        "conditions": patient.conditions,
        "medications": patient.medications,
        "labs": patient.labs,
        "allergies": patient.allergies,
        "visits": patient.visits,
    }
    return json.dumps(data, indent=2)


async def generate_briefing(patient: Patient) -> BriefingResponse:
    """Generate a patient briefing. Uses RAG agent if Qdrant is available, otherwise V1."""
    logger.info(
        "=== Briefing request: patient=%s conditions=%s ===",
        patient.name,
        patient.conditions,
    )
    if _qdrant_available():
        logger.info("Routing -> RAG agent (multi-turn, max_turns=4)")
        from src.agents.briefing_agent import generate_briefing as rag_generate

        return await rag_generate(patient)

    logger.info("Routing -> V1 agent (single-turn, no tools)")
    return await _generate_briefing_v1(patient)


async def _generate_briefing_v1(patient: Patient) -> BriefingResponse:
    """V1 fallback: single-turn agent without tools."""
    patient_json = _serialize_patient(patient)

    options = ClaudeAgentOptions(
        system_prompt=V1_SYSTEM_PROMPT,
        model=settings.ai_model,
        output_format={
            "type": "json_schema",
            "schema": PatientBriefing.model_json_schema(),
        },
        max_turns=2,
        permission_mode="bypassPermissions",
    )

    logger.info(
        "V1 agent: model=%s max_turns=2 patient=%s",
        settings.ai_model,
        patient.name,
    )
    result = None
    try:
        async for message in query(prompt=patient_json, options=options):
            if isinstance(message, AssistantMessage):
                logger.info("V1 AssistantMessage received (model=%s)", message.model)
            elif isinstance(message, ResultMessage):
                logger.info(
                    "V1 ResultMessage: num_turns=%d duration=%dms cost=$%.4f is_error=%s",
                    message.num_turns,
                    message.duration_ms,
                    message.total_cost_usd or 0,
                    message.is_error,
                )
                if not message.is_error and message.structured_output is not None:
                    briefing = PatientBriefing.model_validate(message.structured_output)
                    result = BriefingResponse(
                        **briefing.model_dump(),
                        generated_at=datetime.datetime.now(datetime.UTC),
                    )
                    logger.info(
                        "V1 briefing: %d flags, %d actions",
                        len(result.flags),
                        len(result.suggested_actions),
                    )
                if message.is_error:
                    raise BriefingGenerationError(
                        code="AGENT_ERROR",
                        message=message.result or "Agent returned an error",
                    )
    except BriefingGenerationError:
        raise
    except CLINotFoundError:
        raise BriefingGenerationError(
            code="CLI_NOT_FOUND",
            message="Claude Code CLI not found. Ensure it is installed.",
        )
    except CLIConnectionError as e:
        raise BriefingGenerationError(
            code="CLI_CONNECTION_ERROR",
            message=f"Failed to connect to Claude CLI: {e}",
        )
    except ProcessError as e:
        raise BriefingGenerationError(
            code="PROCESS_ERROR",
            message=f"Agent process failed: {e}",
        )
    except CLIJSONDecodeError as e:
        raise BriefingGenerationError(
            code="JSON_DECODE_ERROR",
            message=f"Failed to parse agent response: {e}",
        )

    if result is not None:
        logger.info("V1 briefing generated successfully")
        return result

    raise BriefingGenerationError(
        code="NO_RESULT",
        message="Agent did not return a result message",
    )


if __name__ == "__main__":
    import asyncio

    # Rich patient record — copied from seed.py (Maria Garcia)
    # No database needed, runs the full agent pipeline standalone.
    patient = Patient(
        name="Maria Garcia",
        date_of_birth=datetime.date(1957, 3, 15),
        gender="F",
        conditions=["Type 2 Diabetes", "Hypertension", "CKD Stage 3"],
        medications=[
            {"name": "Metformin", "dosage": "1000mg", "frequency": "twice daily"},
            {"name": "Lisinopril", "dosage": "20mg", "frequency": "once daily"},
            {"name": "Amlodipine", "dosage": "5mg", "frequency": "once daily"},
            {"name": "Atorvastatin", "dosage": "40mg", "frequency": "once daily"},
        ],
        labs=[
            {
                "name": "HbA1c",
                "value": 7.2,
                "unit": "%",
                "date": "2024-01-15",
                "reference_range": {"min": 4.0, "max": 5.6},
            },
            {
                "name": "eGFR",
                "value": 45,
                "unit": "mL/min/1.73m2",
                "date": "2024-01-15",
                "reference_range": {"min": 60, "max": 120},
            },
            {
                "name": "Creatinine",
                "value": 1.8,
                "unit": "mg/dL",
                "date": "2024-01-15",
                "reference_range": {"min": 0.6, "max": 1.2},
            },
            {
                "name": "Blood Pressure",
                "value": 145,
                "unit": "mmHg systolic",
                "date": "2024-01-15",
                "reference_range": {"min": 90, "max": 130},
            },
            {
                "name": "LDL Cholesterol",
                "value": 110,
                "unit": "mg/dL",
                "date": "2024-01-15",
                "reference_range": {"min": 0, "max": 100},
            },
            {
                "name": "Potassium",
                "value": 4.8,
                "unit": "mEq/L",
                "date": "2024-01-15",
                "reference_range": {"min": 3.5, "max": 5.0},
            },
        ],
        allergies=["Penicillin", "Sulfa drugs"],
        visits=[
            {"date": "2024-01-15", "reason": "Diabetes follow-up"},
            {"date": "2023-10-20", "reason": "CKD monitoring"},
            {"date": "2023-07-12", "reason": "Hypertension check"},
            {"date": "2023-04-05", "reason": "Annual physical"},
        ],
    )

    async def main() -> None:
        result = await generate_briefing(patient)
        print(json.dumps(result.model_dump(), indent=2, default=str))

    asyncio.run(main())
