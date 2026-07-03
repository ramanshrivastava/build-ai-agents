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
from src.services.briefing_service import BriefingGenerationError, _serialize_patient

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


def _proxy_env() -> dict[str, str]:
    """Env vars that route the spawned Claude Code CLI subprocess through the
    configured translation proxy (e.g. LiteLLM → Vertex Gemini).

    Mirrors the per-process env the `glm` shell function sets, but driven from
    app config so deployed environments can use it too. Empty unless
    ANTHROPIC_BASE_URL is set. The SDK merges this over os.environ when spawning
    the CLI (`{**os.environ, **options.env}`), so it overrides cleanly without
    mutating the current process. Only the SDK paths use this; the Managed
    Agents path cannot be re-pointed (server-hosted by Anthropic).
    """
    if not settings.anthropic_base_url:
        return {}
    return {
        "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
        "ANTHROPIC_AUTH_TOKEN": settings.anthropic_auth_token or "dummy",
        # Map every Claude tier the CLI may resolve internally onto the proxy
        # model name, so no background call escapes to real Anthropic.
        "ANTHROPIC_DEFAULT_OPUS_MODEL": settings.ai_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": settings.ai_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": settings.ai_model,
    }


def _build_options(mcp_servers: dict[str, Any]) -> ClaudeAgentOptions:
    """Build the agent options shared by every tool path.

    Only the `mcp_servers` value differs between the in-process and external-HTTP
    paths; the tool name, system prompt, output schema, and turn budget are identical.
    """
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=settings.ai_model,
        mcp_servers=mcp_servers,
        allowed_tools=["mcp__briefing__search_clinical_guidelines"],
        output_format={
            "type": "json_schema",
            "schema": PatientBriefing.model_json_schema(),
        },
        max_turns=4,
        permission_mode="bypassPermissions",
        env=_proxy_env(),
    )


def _http_mcp_servers() -> dict[str, Any]:
    """Build the external HTTP MCP server config for the FastMCP server.

    Adds a bearer token header only when one is configured, matching the
    optional auth on the standalone server (`mcp_server/server.py`).
    """
    config: dict[str, Any] = {"type": "http", "url": settings.external_mcp_url}
    if settings.external_mcp_auth_token:
        config["headers"] = {
            "Authorization": f"Bearer {settings.external_mcp_auth_token}"
        }
    return {"briefing": config}


async def generate_briefing(patient: Patient) -> BriefingResponse:
    """Generate a RAG-augmented briefing using in-process SDK MCP tools."""
    options = _build_options({"briefing": briefing_tools})
    return await _run_briefing(patient, options, label="RAG agent (in-process MCP)")


async def generate_briefing_via_http_mcp(patient: Patient) -> BriefingResponse:
    """Generate a briefing where the search tool is served by an external HTTP MCP server.

    The tool runs in the standalone FastMCP server (`mcp_server/server.py`) reached over
    Streamable HTTP, rather than in-process. Identical behavior otherwise.
    """
    options = _build_options(_http_mcp_servers())
    return await _run_briefing(patient, options, label="HTTP MCP agent")


async def _run_query_to_result(
    prompt: AsyncIterator[dict[str, Any]],
    options: ClaudeAgentOptions,
    *,
    label: str,
) -> ResultMessage:
    """Drive the SDK query() loop to completion and return the ResultMessage.

    Encapsulates the per-turn logging and the CLI/shutdown error handling shared
    by briefing generation and follow-up answers. Raises BriefingGenerationError
    on any agent/CLI failure.
    """
    result: ResultMessage | None = None
    turn = 0
    try:
        async for message in query(prompt=prompt, options=options):
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
                if message.is_error:
                    raise BriefingGenerationError(
                        code="AGENT_ERROR",
                        message=message.result or "Agent returned an error",
                    )
                result = message
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

    if result is None:
        raise BriefingGenerationError(
            code="NO_RESULT",
            message="Agent did not return a result message",
        )
    return result


async def _run_briefing(
    patient: Patient,
    options: ClaudeAgentOptions,
    *,
    label: str,
) -> BriefingResponse:
    """Run the multi-turn agent loop for the given options and return the briefing."""
    patient_json = _serialize_patient(patient)

    logger.info(
        "Starting %s: model=%s routing=%s max_turns=%d tools=%s",
        label,
        settings.ai_model,
        settings.anthropic_base_url or "direct (Anthropic)",
        4,
        options.allowed_tools,
    )
    logger.info("Patient: %s, conditions=%s", patient.name, patient.conditions)
    logger.debug("Patient JSON prompt:\n%s", patient_json)

    message = await _run_query_to_result(_as_stream(patient_json), options, label=label)
    if message.structured_output is None:
        raise BriefingGenerationError(
            code="NO_RESULT",
            message="Agent did not return structured output",
        )
    briefing = PatientBriefing.model_validate(message.structured_output)
    logger.info(
        "%s complete: %d flags, %d actions",
        label,
        len(briefing.flags),
        len(briefing.suggested_actions),
    )
    return BriefingResponse(
        **briefing.model_dump(),
        generated_at=datetime.datetime.now(datetime.UTC),
    )


# --- Follow-up Q&A (conversational) ---

FOLLOWUP_SYSTEM_PROMPT = """\
You are a clinical decision support assistant. The physician has received a \
pre-consultation briefing for a patient and is now asking follow-up questions.

Answer concisely. Ground every clinical claim in the provided briefing or in \
evidence retrieved via the search_clinical_guidelines tool, and cite sources as \
[source_id]. If the question cannot be answered from the record or guidelines, \
say so explicitly rather than guessing.
"""


def _build_followup_options(mcp_servers: dict[str, Any]) -> ClaudeAgentOptions:
    """Options for a follow-up turn: same tool access, free-text (no schema)."""
    return ClaudeAgentOptions(
        system_prompt=FOLLOWUP_SYSTEM_PROMPT,
        model=settings.ai_model,
        mcp_servers=mcp_servers,
        allowed_tools=["mcp__briefing__search_clinical_guidelines"],
        max_turns=4,
        permission_mode="bypassPermissions",
        env=_proxy_env(),
    )


async def answer_followup_question(
    patient: Patient,
    briefing_content: dict[str, Any],
    history: list[tuple[str, str]],
    question: str,
) -> str:
    """Answer a clinician's follow-up question about an existing briefing.

    Free-text answer (no structured output). The RAG tool stays available so the
    agent can look up guidelines. Reuses the in-process MCP tool server and the
    same proxy routing as briefing generation. `history` is the prior turns as
    (role, content) pairs.
    """
    patient_json = _serialize_patient(patient)
    sections = [
        f"PATIENT RECORD (JSON):\n{patient_json}",
        "PRE-CONSULTATION BRIEFING (already generated for this patient):\n"
        + json.dumps(briefing_content, default=str, indent=2),
    ]
    if history:
        transcript = "\n\n".join(
            f"{'Physician' if role == 'user' else 'Assistant'}: {text}"
            for role, text in history
        )
        sections.append("PRIOR FOLLOW-UP Q&A IN THIS CONVERSATION:\n" + transcript)
    sections.append("PHYSICIAN'S NEW QUESTION:\n" + question)
    prompt = "\n\n".join(sections)

    logger.info(
        "Starting follow-up: model=%s routing=%s prior_turns=%d",
        settings.ai_model,
        settings.anthropic_base_url or "direct (Anthropic)",
        len(history),
    )
    options = _build_followup_options({"briefing": briefing_tools})
    message = await _run_query_to_result(
        _as_stream(prompt), options, label="follow-up agent"
    )
    return message.result or ""
