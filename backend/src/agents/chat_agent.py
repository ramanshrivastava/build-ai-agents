"""Unified patient-chat agent: ClaudeSDKClient + session resume + briefing skill.

This module demonstrates the SDK patterns the briefing paths don't:

- **ClaudeSDKClient vs query()** — `query()` is one-shot; `ClaudeSDKClient` is
  the SDK's interactive interface (the same loop Claude Code itself runs). We
  scope one client to one HTTP request and rely on `resume` for continuity,
  because a web server can't hold subprocesses between requests (restarts and
  multiple workers would silently kill them). The client also keeps stdin open
  by design, so the `_as_stream` workaround `query()` needs for MCP tools does
  not apply here.
- **resume=session_id** — the SDK stores the full transcript client-side
  (~/.claude/projects/, keyed by cwd), so passing the previous turn's
  session_id replays the whole conversation: the web equivalent of
  `claude --resume`. Works with any model behind the proxy, since the provider
  never holds session state.
- **Skills** — the /briefing behavior lives in
  `agent_home/.claude/skills/briefing/SKILL.md`, loaded only because we pass
  `setting_sources=["project"]` with `cwd=AGENT_HOME` (the SDK loads NO
  filesystem settings by default). `cwd` must stay constant across turns or
  resume can't find the transcript.
- **Tool input schema as structured output** — `publish_briefing`'s input
  schema IS `PatientBriefing.model_json_schema()`, so the SDK validates the
  agent's briefing against our Pydantic contract at the tool boundary. That is
  how a free-flowing chat can still emit schema-guaranteed artifacts.
"""

from __future__ import annotations

import logging

from asyncio import Queue
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ProcessError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)
from pydantic import ValidationError

from src.agents.briefing_agent import _http_mcp_servers, _proxy_env
from src.config import settings
from src.models.schemas import BriefingResponse, PatientBriefing
from src.services.briefing_service import BriefingGenerationError

logger = logging.getLogger(__name__)

# The agent's working directory: skills live under its .claude/, and the SDK
# keys session transcripts by cwd — so this path must be identical every turn.
AGENT_HOME = Path(__file__).resolve().parents[2] / "agent_home"

# One SSE frame: (event kind, JSON-serializable payload).
ChatEvent = tuple[str, dict[str, Any]]

CHAT_SYSTEM_PROMPT = """\
You are a clinical decision support assistant helping a physician prepare for
and reason about a single patient's consultation. The patient's full record is
provided at the start of the conversation.

- Answer concisely; physicians need quick, scannable information.
- Ground clinical claims in evidence: use the search_clinical_guidelines tool
  and cite sources as [source_id]. If no relevant guideline is found, say so
  rather than inventing backing.
- Only discuss what is visible in the provided patient data.
- When the physician asks for a briefing or sends /briefing, the briefing
  skill defines the exact workflow — follow it.
"""


def make_publish_tool(queue: Queue[ChatEvent], patient_id: int):
    """Build the publish_briefing tool bound to this request's queue + patient.

    A factory (rather than a module-level tool) because the handler must close
    over per-request state: which patient to attach the briefing to, and which
    SSE queue to notify. The handler runs in the FastAPI process's event loop —
    in-process SDK MCP tools are plain coroutines, not subprocesses — which is
    what lets it write to the database and the live SSE stream directly.
    """

    @tool(
        "publish_briefing",
        "Publish the completed structured pre-consultation briefing to the "
        "physician's dashboard. Call exactly once, after evidence gathering.",
        PatientBriefing.model_json_schema(),
    )
    async def publish_briefing(args: dict[str, Any]) -> dict[str, Any]:
        # Import here so tests can patch src.database.async_session and to
        # avoid creating the engine as an import side effect of this module.
        from src.database import async_session
        from src.services.briefing_chat_service import store_briefing

        try:
            briefing = PatientBriefing.model_validate(args)
        except ValidationError as exc:
            # isError sends the message back to the model so it can correct
            # the payload and retry, instead of failing the whole turn.
            # Log without the error detail — pydantic messages can echo
            # rejected input, which here is patient briefing content.
            logger.warning("publish_briefing validation failed")
            return {
                "content": [{"type": "text", "text": f"Invalid briefing: {exc}"}],
                "isError": True,
            }

        async with async_session() as session:
            stored = await store_briefing(
                session, patient_id, briefing.model_dump(mode="json")
            )
        response = BriefingResponse(
            **briefing.model_dump(),
            id=stored.id,
            generated_at=stored.created_at,
        )
        await queue.put(("briefing_published", response.model_dump(mode="json")))
        logger.info(
            "Published briefing %d for patient %d (%d flags)",
            stored.id,
            patient_id,
            len(briefing.flags),
        )
        return {
            "content": [
                {"type": "text", "text": f"Briefing published (id={stored.id})."}
            ]
        }

    return publish_briefing


def build_chat_options(
    queue: Queue[ChatEvent],
    patient_id: int,
    resume_session_id: str | None,
    patient_json: str,
) -> ClaudeAgentOptions:
    """Options for one chat turn.

    Two MCP servers under distinct keys (tool names embed the server key as
    mcp__<key>__<tool>): the guidelines search served over HTTP by the
    standalone FastMCP server, and the in-process publisher bound to this
    request. "Skill" must be allowed for the /briefing skill to run.

    The patient record rides in the system prompt rather than the first user
    message: user messages must stay verbatim so "/briefing" is recognized as
    a slash command, and the system prompt is re-sent with every turn anyway.
    """
    publisher = create_sdk_mcp_server(
        name="publisher",
        version="1.0.0",
        tools=[make_publish_tool(queue, patient_id)],
    )
    return ClaudeAgentOptions(
        system_prompt=f"{CHAT_SYSTEM_PROMPT}\nPATIENT RECORD (JSON):\n{patient_json}",
        model=settings.ai_model,
        mcp_servers={
            "guidelines": _http_mcp_servers()["briefing"],
            "publisher": publisher,
        },
        allowed_tools=[
            "Skill",
            "mcp__guidelines__search_clinical_guidelines",
            "mcp__publisher__publish_briefing",
        ],
        # A briefing turn is skill + several searches + publish; well above
        # the briefing endpoints' max_turns=4.
        max_turns=12,
        # Extended thinking: without this the request carries no thinking
        # param, and Gemini (via LiteLLM -> Vertex thinkingConfig) reasons
        # invisibly — thought traces are only returned when explicitly enabled.
        thinking=(
            {"type": "enabled", "budget_tokens": settings.ai_thinking_budget}
            if settings.ai_thinking_budget > 0
            else None
        ),
        permission_mode="bypassPermissions",
        env=_proxy_env(),
        cwd=str(AGENT_HOME),
        setting_sources=["project"],
        resume=resume_session_id,
    )


def _short_tool_name(name: str) -> str:
    """mcp__guidelines__search_clinical_guidelines -> search_clinical_guidelines."""
    return name.split("__")[-1]


RESULT_PREVIEW_LIMIT = 600


def _result_preview(content: Any) -> str:
    """Flatten a ToolResultBlock's content into a short display string.

    Content arrives as a plain string or a list of content dicts; anything
    beyond the preview limit is truncated — the full result already reached
    the model, this copy is only for the UI trace.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        text = content
    else:
        text = "\n".join(
            d.get("text", "")
            for d in content
            if isinstance(d, dict) and d.get("type") == "text"
        )
    if len(text) > RESULT_PREVIEW_LIMIT:
        return text[:RESULT_PREVIEW_LIMIT] + "…"
    return text


async def drive_chat_turn(
    prompt: str,
    options: ClaudeAgentOptions,
    queue: Queue[ChatEvent],
) -> tuple[str | None, str, list[dict[str, Any]]]:
    """Run one chat turn, translating SDK messages into SSE events on the queue.

    Returns (session_id, assistant_text, trace). The trace is the ordered list
    of parts the agent produced — thinking, tool calls (with inputs and result
    previews), and text — persisted so the UI can replay the agent's work
    after a refresh. The caller owns the terminal done/error event.
    Raises BriefingGenerationError on agent/CLI failure (same error taxonomy
    as the briefing paths, so the router maps them identically).
    """
    session_id: str | None = None
    text_parts: list[str] = []
    trace: list[dict[str, Any]] = []
    # tool_use_id -> its trace entry, so results can be attached when they
    # come back (as UserMessage tool-result blocks) a few messages later.
    pending_tools: dict[str, dict[str, Any]] = {}
    result: ResultMessage | None = None
    try:
        async with ClaudeSDKClient(options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, SystemMessage):
                    if message.subtype == "init":
                        session_id = message.data.get("session_id")
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                            trace.append({"type": "text", "text": block.text})
                            await queue.put(("text", {"text": block.text}))
                        elif isinstance(block, ThinkingBlock):
                            # Reasoning tokens (when the model/proxy surfaces
                            # them) — streamed and persisted like any part.
                            trace.append({"type": "thinking", "text": block.thinking})
                            await queue.put(("thinking", {"text": block.thinking}))
                        elif isinstance(block, ToolUseBlock):
                            short = _short_tool_name(block.name)
                            # publish_briefing's input is the entire briefing;
                            # the briefing_published event already carries it.
                            payload = {} if short == "publish_briefing" else block.input
                            entry: dict[str, Any] = {
                                "type": "tool_use",
                                "id": block.id,
                                "tool": short,
                                "input": payload,
                                "result": None,
                            }
                            trace.append(entry)
                            pending_tools[block.id] = entry
                            await queue.put(
                                (
                                    "tool_use",
                                    {"id": block.id, "tool": short, "input": payload},
                                )
                            )
                elif isinstance(message, UserMessage):
                    # In the SDK loop, UserMessage = tool results fed back.
                    blocks = (
                        message.content if isinstance(message.content, list) else []
                    )
                    for block in blocks:
                        if not isinstance(block, ToolResultBlock):
                            continue
                        outcome = {
                            "is_error": bool(block.is_error),
                            "content": _result_preview(block.content),
                        }
                        pending = pending_tools.pop(block.tool_use_id, None)
                        if pending is not None:
                            pending["result"] = outcome
                        await queue.put(
                            (
                                "tool_result",
                                {"tool_use_id": block.tool_use_id, **outcome},
                            )
                        )
                elif isinstance(message, ResultMessage):
                    session_id = message.session_id or session_id
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
        if result is None:
            raise BriefingGenerationError(
                code="CLI_CONNECTION_ERROR",
                message=f"Failed to connect to Claude CLI: {e}",
            )
        logger.warning("CLIConnectionError after result received (ignoring): %s", e)
    except BaseExceptionGroup as eg:
        # The SDK task group can wrap CLIConnectionError during shutdown — a
        # race between transport close and in-flight control handlers. Safe to
        # ignore once we already hold a result. (Same handling as
        # briefing_agent._run_query_to_result.)
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
            code="PROCESS_ERROR", message=f"Agent process failed: {e}"
        )
    except CLIJSONDecodeError as e:
        raise BriefingGenerationError(
            code="JSON_DECODE_ERROR", message=f"Failed to parse agent response: {e}"
        )

    if result is None:
        raise BriefingGenerationError(
            code="NO_RESULT", message="Agent did not return a result message"
        )
    logger.info(
        "Chat turn complete: session=%s num_turns=%d cost=$%.4f",
        session_id,
        result.num_turns,
        result.total_cost_usd or 0,
    )
    return session_id, "".join(text_parts), trace
