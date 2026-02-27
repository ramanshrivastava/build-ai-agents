"""RAG-augmented briefing agent with clinical guideline search tool."""

from __future__ import annotations

import datetime
import json
import logging

from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    ClaudeAgentOptions,
    ProcessError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    query,
)

from src.agents.tools import search_clinical_guidelines
from src.config import settings
from src.models.orm import Patient
from src.models.schemas import BriefingResponse, PatientBriefing

logger = logging.getLogger(__name__)

# --- MCP Server with tools ---

briefing_tools = create_sdk_mcp_server(
    name="briefing",
    version="1.0.0",
    tools=[search_clinical_guidelines],
)

# --- System Prompt ---

SYSTEM_PROMPT = """\
You are a clinical decision support assistant preparing pre-consultation \
briefings for physicians. You have access to a clinical guidelines search tool.

WORKFLOW:
1. Review the patient record carefully
2. Search for relevant clinical guidelines for their conditions
3. Search for drug interactions if they have multiple medications
4. Generate a briefing grounded in the retrieved evidence
5. Cite sources using [source_id] for every clinical claim

INPUT: Patient record in JSON format with demographics, conditions, \
medications, lab results (with reference ranges), allergies, and visits.

OUTPUT: Structured briefing with flags, summary, and suggested actions.

SEARCH TOOL USAGE:
- Call search_clinical_guidelines for each major condition
- Search for drug interactions when the patient has 2+ medications
- Use specific clinical queries (e.g., "metformin renal dosing eGFR 45") \
not vague ones (e.g., "diabetes")

FLAG GUIDELINES:
- category "labs": Flag lab values outside reference ranges. Cite the \
guideline that defines the target range.
- category "medications": Flag medication concerns. Cite drug interaction \
or dosing guidelines.
- category "screenings": Flag overdue preventive screenings based on \
age/gender/conditions.
- category "ai_insight": Flag clinical patterns across the data, grounded \
in retrieved evidence.
- severity "critical": Immediate clinical concern.
- severity "warning": Needs attention this visit.
- severity "info": Worth noting but not urgent.
- source is always "ai".
- Include suggested_action when a concrete next step exists.

SUMMARY GUIDELINES:
- one_liner: Single sentence capturing the clinical picture and visit context.
- key_conditions: List active conditions from the record.
- relevant_history: Brief paragraph of clinically relevant context. \
Reference retrieved guidelines where applicable.

SUGGESTED ACTIONS (3-5):
- Prioritize by clinical urgency (priority 1 = most urgent).
- Ground each action in retrieved evidence where possible.
- Include a brief reason explaining why.

CITATION RULES:
- Every clinical claim MUST reference a source_id from search results.
- If no relevant guidelines were found, state this explicitly.
- Do NOT make clinical claims without source backing.
- Format citations as [1], [2], etc. in description text.

CONSTRAINTS:
- Only flag issues visible in the provided data.
- If the search returns no relevant guidelines, generate the briefing \
based on the patient data and note that guidelines were unavailable.
- Be concise. Physicians need quick, scannable information.
"""


class BriefingGenerationError(Exception):
    """Raised when briefing generation fails."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


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


def _log_assistant_message(message: AssistantMessage, turn: int) -> None:
    """Log each content block in an assistant message."""
    logger.info("[turn %d] AssistantMessage (model=%s)", turn, message.model)
    for block in message.content:
        if isinstance(block, TextBlock):
            preview = block.text[:200] + ("..." if len(block.text) > 200 else "")
            logger.info("[turn %d]   TextBlock: %s", turn, preview)
        elif isinstance(block, ThinkingBlock):
            preview = block.thinking[:200] + (
                "..." if len(block.thinking) > 200 else ""
            )
            logger.debug("[turn %d]   ThinkingBlock: %s", turn, preview)
        elif isinstance(block, ToolUseBlock):
            logger.info(
                "[turn %d]   ToolUseBlock: tool=%s id=%s input=%s",
                turn,
                block.name,
                block.id,
                json.dumps(block.input, default=str),
            )
        elif isinstance(block, ToolResultBlock):
            content_preview = str(block.content)[:300] if block.content else "(empty)"
            logger.info(
                "[turn %d]   ToolResultBlock: tool_use_id=%s is_error=%s content=%s",
                turn,
                block.tool_use_id,
                block.is_error,
                content_preview,
            )


def _log_result_message(message: ResultMessage) -> None:
    """Log the final result message with stats."""
    logger.info(
        "ResultMessage: subtype=%s num_turns=%d duration=%dms api_duration=%dms "
        "cost=$%.4f is_error=%s",
        message.subtype,
        message.num_turns,
        message.duration_ms,
        message.duration_api_ms,
        message.total_cost_usd or 0,
        message.is_error,
    )
    if message.usage:
        logger.info("  Usage: %s", json.dumps(message.usage, default=str))
    if message.is_error:
        logger.error("  Error result: %s", message.result)
    elif message.structured_output:
        # Log a summary of the structured output (flags count, actions count)
        output = message.structured_output
        flags = output.get("flags", []) if isinstance(output, dict) else []
        actions = (
            output.get("suggested_actions", []) if isinstance(output, dict) else []
        )
        logger.info(
            "  Structured output: %d flags, %d suggested_actions",
            len(flags),
            len(actions),
        )
        for flag in flags:
            logger.debug(
                "    Flag: [%s/%s] %s",
                flag.get("category"),
                flag.get("severity"),
                flag.get("title"),
            )


async def _as_stream(text: str) -> AsyncIterator[dict[str, Any]]:
    """Wrap a string prompt as a streaming input.

    The Claude Agent SDK closes stdin immediately for string prompts, which
    prevents MCP tool responses from being written back.  Streaming mode keeps
    stdin open until the first result, enabling bidirectional communication.
    """
    yield {"type": "user", "message": {"role": "user", "content": text}}


async def generate_briefing(patient: Patient) -> BriefingResponse:
    """Generate a RAG-augmented patient briefing using the multi-turn agent."""
    patient_json = _serialize_patient(patient)

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=settings.ai_model,
        mcp_servers={"briefing": briefing_tools},
        allowed_tools=["mcp__briefing__search_clinical_guidelines"],
        output_format={
            "type": "json_schema",
            "schema": PatientBriefing.model_json_schema(),
        },
        max_turns=4,
        permission_mode="bypassPermissions",
    )

    logger.info(
        "Starting RAG agent: model=%s max_turns=%d tools=%s",
        settings.ai_model,
        4,
        options.allowed_tools,
    )
    logger.info("Patient: %s, conditions=%s", patient.name, patient.conditions)
    logger.debug("Patient JSON prompt:\n%s", patient_json)

    result = None
    turn = 0
    try:
        async for message in query(prompt=_as_stream(patient_json), options=options):
            if isinstance(message, AssistantMessage):
                turn += 1
                _log_assistant_message(message, turn)
            elif isinstance(message, UserMessage):
                # UserMessage in multi-turn = tool results fed back to agent
                logger.info(
                    "[turn %d] UserMessage (tool result fed back to agent)", turn
                )
                if message.tool_use_result:
                    logger.debug(
                        "[turn %d]   tool_use_result: %s",
                        turn,
                        str(message.tool_use_result)[:300],
                    )
            elif isinstance(message, SystemMessage):
                logger.debug(
                    "SystemMessage: subtype=%s data=%s",
                    message.subtype,
                    str(message.data)[:200],
                )
            elif isinstance(message, ResultMessage):
                _log_result_message(message)
                if not message.is_error and message.structured_output is not None:
                    briefing = PatientBriefing.model_validate(message.structured_output)
                    result = BriefingResponse(
                        **briefing.model_dump(),
                        generated_at=datetime.datetime.now(datetime.UTC),
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
        if result is not None:
            logger.warning("CLIConnectionError after result received (ignoring): %s", e)
        else:
            raise BriefingGenerationError(
                code="CLI_CONNECTION_ERROR",
                message=f"Failed to connect to Claude CLI: {e}",
            )
    except BaseExceptionGroup as eg:
        # SDK task group wraps CLIConnectionError in ExceptionGroup during
        # query.close() — a race between transport shutdown and in-flight
        # control request handlers. Safe to ignore if we already have a result.
        cli_errors = eg.subgroup(CLIConnectionError)
        if cli_errors and result is not None:
            logger.warning(
                "CLIConnectionError in task group after result (ignoring): %s",
                cli_errors.exceptions[0],
            )
        elif cli_errors:
            raise BriefingGenerationError(
                code="CLI_CONNECTION_ERROR",
                message=f"Failed to connect to Claude CLI: {cli_errors.exceptions[0]}",
            )
        else:
            raise
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
        logger.info(
            "RAG briefing complete: %d flags, %d actions",
            len(result.flags),
            len(result.suggested_actions),
        )
        return result

    raise BriefingGenerationError(
        code="NO_RESULT",
        message="Agent did not return a result message",
    )
