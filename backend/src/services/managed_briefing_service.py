"""Claude Managed Agents briefing service."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re
from typing import Any

from anthropic import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncAnthropic,
    BadRequestError,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.tools import search_clinical_guidelines
from src.config import settings
from src.models.orm import ManagedAgentSession, Patient
from src.models.schemas import BriefingResponse, PatientBriefing
from src.services.briefing_service import BriefingGenerationError, _serialize_patient

logger = logging.getLogger(__name__)

MANAGED_SYSTEM_PROMPT = """\
You are the managed-runtime version of the AI Doctor briefing agent.

You prepare pre-consultation briefings for physicians from synthetic patient
records in this course repo. Treat the latest patient JSON sent by the user as
the source of truth, even when the session contains older messages for the same
patient.

You have one custom tool:
- search_clinical_guidelines(query, specialty, max_results)

Workflow:
1. Review the latest patient JSON carefully.
2. Search for relevant clinical guidelines for major conditions.
3. Search for drug interactions when the patient has 2+ medications.
4. Generate a concise briefing grounded in retrieved evidence.
5. Cite sources as [source_id] in clinical claims.

Return only JSON matching this shape:
{
  "flags": [
    {
      "category": "labs|medications|screenings|ai_insight",
      "severity": "critical|warning|info",
      "title": "string",
      "description": "string",
      "source": "ai",
      "suggested_action": "string or null"
    }
  ],
  "summary": {
    "one_liner": "string",
    "key_conditions": ["string"],
    "relevant_history": "string"
  },
  "suggested_actions": [
    {"action": "string", "reason": "string", "priority": 1}
  ]
}

Do not wrap the JSON in Markdown. Do not include prose before or after it.
"""

TOOL_SCHEMA: dict[str, Any] = {
    "type": "custom",
    "name": "search_clinical_guidelines",
    "description": (
        "Search clinical guidelines, drug interactions, and protocols. "
        "Returns relevant passages with source citations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "specialty": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
    },
}


def _configured() -> bool:
    """Return True when all Managed Agents settings are present."""
    return bool(
        settings.anthropic_api_key
        and settings.managed_agent_id
        and settings.managed_environment_id
    )


def _client() -> AsyncAnthropic:
    """Build an AsyncAnthropic client from settings."""
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _get_or_create_session(
    db: AsyncSession,
    client: AsyncAnthropic,
    patient: Patient,
) -> ManagedAgentSession:
    result = await db.execute(
        select(ManagedAgentSession).where(ManagedAgentSession.patient_id == patient.id)
    )
    mapping = result.scalar_one_or_none()
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

    if mapping is not None:
        mapping.last_used_at = now
        await db.commit()
        await db.refresh(mapping)
        return mapping

    remote_session = await client.beta.sessions.create(
        agent=settings.managed_agent_id,
        environment_id=settings.managed_environment_id,
        title=f"AI Doctor synthetic patient {patient.id}",
        metadata={"patient_id": str(patient.id), "course": "build-ai-agents"},
    )
    mapping = ManagedAgentSession(
        patient_id=patient.id,
        session_id=remote_session.id,
        last_used_at=now,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    logger.info(
        "Created managed-agent session patient_id=%s session_id=%s",
        patient.id,
        mapping.session_id,
    )
    return mapping


async def _list_event_ids(client: AsyncAnthropic, session_id: str) -> set[str]:
    """Snapshot existing event IDs, answering orphaned tool calls first.

    An interrupted run can leave an `agent.custom_tool_use` without its
    `user.custom_tool_result`, which blocks the session forever. Answer any
    such orphan with an error result so the reused session can make progress.
    """
    seen: set[str] = set()
    tool_use_ids: set[str] = set()
    answered_ids: set[str] = set()
    async for event in client.beta.sessions.events.list(
        session_id,
        order="asc",
        limit=100,
    ):
        event_id = getattr(event, "id", None)
        if not event_id:
            continue
        seen.add(event_id)
        event_type = getattr(event, "type", "")
        if event_type == "agent.custom_tool_use":
            tool_use_ids.add(event_id)
        elif event_type == "user.custom_tool_result":
            answered_ids.add(getattr(event, "custom_tool_use_id", ""))

    orphan_ids = tool_use_ids - answered_ids
    for orphan_id in orphan_ids:
        logger.warning(
            "Answering orphaned tool call %s in session %s", orphan_id, session_id
        )
        await _send_tool_result(
            client,
            session_id,
            orphan_id,
            "Orphaned tool call from an interrupted run; ignore it and use "
            "the latest patient message.",
            is_error=True,
        )
    if orphan_ids:
        # Answering an orphan resumes the stale turn; interrupt it so the
        # session settles to idle before the new patient message.
        await _interrupt_session(client, session_id)
    return seen


def _patient_prompt(patient_json: str) -> str:
    """Build the per-run user message wrapping the latest patient JSON."""
    return (
        "Generate a structured pre-consultation briefing for this synthetic "
        "patient. Use the latest JSON below as the source of truth for this run. "
        "Return only JSON matching the requested schema.\n\n"
        f"PATIENT_JSON:\n{patient_json}"
    )


async def _send_patient_message(
    client: AsyncAnthropic,
    session_id: str,
    patient_json: str,
) -> None:
    await client.beta.sessions.events.send(
        session_id,
        events=[
            {
                "type": "user.message",
                "content": [{"type": "text", "text": _patient_prompt(patient_json)}],
            }
        ],
    )


async def _send_patient_message_with_recovery(
    client: AsyncAnthropic,
    session_id: str,
    patient_json: str,
    seen: set[str],
) -> None:
    """Send the patient message, healing a session still settling after recovery.

    Right after orphaned tool calls are answered, the API can briefly keep the
    session in a waiting/running state and reject `user.message`. Re-run the
    recovery pass and retry with backoff before giving up.
    """
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            await _send_patient_message(client, session_id, patient_json)
            return
        except BadRequestError as exc:
            if "waiting on responses" not in str(exc) or attempt == max_attempts:
                raise
            logger.warning(
                "Session %s not ready for user.message (attempt %d/%d): %s",
                session_id,
                attempt,
                max_attempts,
                exc,
            )
            await asyncio.sleep(float(attempt))
            seen |= await _list_event_ids(client, session_id)


async def _send_tool_result(
    client: AsyncAnthropic,
    session_id: str,
    tool_use_id: str,
    text: str,
    *,
    is_error: bool = False,
) -> None:
    await client.beta.sessions.events.send(
        session_id,
        events=[
            {
                "type": "user.custom_tool_result",
                "custom_tool_use_id": tool_use_id,
                "content": [{"type": "text", "text": text}],
                "is_error": is_error,
            }
        ],
    )


async def _interrupt_session(client: AsyncAnthropic, session_id: str) -> None:
    """Best-effort interrupt so a bail-out leaves the session idle, not wedged."""
    try:
        await client.beta.sessions.events.send(
            session_id,
            events=[{"type": "user.interrupt"}],
        )
    except (APIConnectionError, APITimeoutError, APIError) as exc:
        logger.warning("Failed to interrupt session %s: %s", session_id, exc)


async def _abandon_turn(
    client: AsyncAnthropic,
    session_id: str,
    tool_use_id: str,
) -> None:
    """Answer the pending tool call with an error, then interrupt the turn.

    Raising out of the event loop while a tool call is unanswered would wedge
    the session: it keeps waiting for the result and rejects new user messages.
    """
    try:
        await _send_tool_result(
            client,
            session_id,
            tool_use_id,
            "Tool budget exhausted; stopping this run.",
            is_error=True,
        )
    except (APIConnectionError, APITimeoutError, APIError) as exc:
        logger.warning(
            "Failed to answer tool call %s during bail-out: %s", tool_use_id, exc
        )
    await _interrupt_session(client, session_id)


async def _handle_custom_tool(
    client: AsyncAnthropic,
    session_id: str,
    event: Any,
) -> None:
    if getattr(event, "name", "") != "search_clinical_guidelines":
        await _send_tool_result(
            client,
            session_id,
            event.id,
            f"Unknown custom tool: {getattr(event, 'name', '')}",
            is_error=True,
        )
        return

    tool_result = await search_clinical_guidelines.handler(dict(event.input))
    content = tool_result.get("content", [])
    text = "\n".join(
        block.get("text", "") for block in content if block.get("type") == "text"
    )
    await _send_tool_result(
        client,
        session_id,
        event.id,
        text or "(tool returned no text)",
        is_error=bool(tool_result.get("isError")),
    )


def _append_agent_message_text(event: Any, chunks: list[str]) -> None:
    for block in getattr(event, "content", []):
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
        if match:
            stripped = match.group(1).strip()
    return json.loads(stripped)


async def _wait_for_briefing_json(
    client: AsyncAnthropic,
    session_id: str,
    seen: set[str],
) -> dict[str, Any]:
    deadline = (
        asyncio.get_running_loop().time()
        + settings.managed_agent_session_timeout_seconds
    )
    agent_text: list[str] = []
    handled_tool_ids: set[str] = set()

    while asyncio.get_running_loop().time() < deadline:
        made_progress = False
        async for event in client.beta.sessions.events.list(
            session_id,
            order="asc",
            limit=100,
        ):
            event_id = getattr(event, "id", None)
            if not event_id or event_id in seen:
                continue
            seen.add(event_id)
            made_progress = True

            event_type = getattr(event, "type", "")
            logger.debug("Managed agent event: %s", event_type)

            if event_type == "agent.message":
                _append_agent_message_text(event, agent_text)
            elif event_type == "agent.custom_tool_use":
                if event_id not in handled_tool_ids:
                    if len(handled_tool_ids) >= settings.managed_agent_max_tool_rounds:
                        await _abandon_turn(client, session_id, event_id)
                        raise BriefingGenerationError(
                            code="MANAGED_AGENTS_TIMEOUT",
                            message="Managed agent exceeded custom tool round limit",
                        )
                    await _handle_custom_tool(client, session_id, event)
                    handled_tool_ids.add(event_id)
            elif event_type == "session.error":
                error = getattr(event, "error", None)
                message = getattr(error, "message", "Managed agent session error")
                raise BriefingGenerationError(
                    code="MANAGED_AGENTS_API_ERROR",
                    message=message,
                )
            elif event_type == "session.status_idle":
                stop_reason = getattr(event, "stop_reason", None)
                if getattr(stop_reason, "type", "") == "end_turn" and agent_text:
                    try:
                        return _extract_json(agent_text[-1])
                    except (json.JSONDecodeError, TypeError) as exc:
                        raise BriefingGenerationError(
                            code="MANAGED_AGENTS_INVALID_OUTPUT",
                            message=f"Managed agent returned invalid JSON: {exc}",
                        ) from exc

        if not made_progress:
            await asyncio.sleep(0.5)

    # Leave the session idle rather than mid-turn before giving up.
    await _interrupt_session(client, session_id)
    raise BriefingGenerationError(
        code="MANAGED_AGENTS_TIMEOUT",
        message="Timed out waiting for managed agent result",
    )


async def generate_managed_briefing(
    db: AsyncSession,
    patient: Patient,
) -> BriefingResponse:
    """Generate a patient briefing through Claude Managed Agents."""
    if not _configured():
        raise BriefingGenerationError(
            code="MANAGED_AGENTS_NOT_CONFIGURED",
            message=(
                "Claude Managed Agents is not configured. Run "
                "`cd backend && uv run python ../scripts/setup_managed_agent.py` "
                "and set MANAGED_AGENT_ID and MANAGED_ENVIRONMENT_ID."
            ),
        )

    patient_json = _serialize_patient(patient)
    client = _client()

    try:
        mapping = await _get_or_create_session(db, client, patient)
        seen = await _list_event_ids(client, mapping.session_id)
        await _send_patient_message_with_recovery(
            client,
            mapping.session_id,
            patient_json,
            seen,
        )
        structured_output = await _wait_for_briefing_json(
            client,
            mapping.session_id,
            seen,
        )
    except BriefingGenerationError:
        raise
    except (APIConnectionError, APITimeoutError, APIError) as exc:
        raise BriefingGenerationError(
            code="MANAGED_AGENTS_API_ERROR",
            message=f"Claude Managed Agents API request failed: {exc}",
        ) from exc

    try:
        briefing = PatientBriefing.model_validate(structured_output)
    except Exception as exc:
        raise BriefingGenerationError(
            code="MANAGED_AGENTS_INVALID_OUTPUT",
            message=f"Managed agent output did not match PatientBriefing: {exc}",
        ) from exc

    return BriefingResponse(
        **briefing.model_dump(),
        generated_at=datetime.datetime.now(datetime.UTC),
    )


async def reset_managed_session(db: AsyncSession, patient_id: int) -> None:
    """Delete the local session mapping and best-effort delete the remote session."""
    result = await db.execute(
        select(ManagedAgentSession).where(ManagedAgentSession.patient_id == patient_id)
    )
    mapping = result.scalar_one_or_none()
    if mapping and settings.anthropic_api_key:
        try:
            await _client().beta.sessions.delete(mapping.session_id)
        except (APIConnectionError, APITimeoutError, APIError) as exc:
            logger.warning(
                "Failed to delete remote managed-agent session %s: %s",
                mapping.session_id,
                exc,
            )

    await db.execute(
        delete(ManagedAgentSession).where(ManagedAgentSession.patient_id == patient_id)
    )
    await db.commit()
