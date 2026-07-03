"""Unified patient chat: persistence + SSE orchestration around the chat agent.

The streaming shape here is a fan-in: the agent turn runs as a background task
and *two* producers write to one asyncio.Queue — drive_chat_turn (text and tool
activity, in message order) and the publish_briefing tool handler (the
briefing artifact, mid-turn). The single consumer below drains the queue and
frames each item as one Server-Sent Event, so the HTTP response is a live
merged view of everything the agent is doing.
"""

from __future__ import annotations

import asyncio
import json
import logging

from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.chat_agent import ChatEvent, build_chat_options, drive_chat_turn
from src.models.orm import Briefing, Conversation, ConversationMessage, Patient
from src.models.schemas import (
    BriefingResponse,
    ChatHistoryResponse,
    ChatMessageOut,
)
from src.services.briefing_service import BriefingGenerationError, _serialize_patient

logger = logging.getLogger(__name__)

# One in-flight turn per patient: the SDK session transcript is a single
# linear history, so concurrent turns would race on resume.
_locks: dict[int, asyncio.Lock] = {}


def _lock_for(patient_id: int) -> asyncio.Lock:
    return _locks.setdefault(patient_id, asyncio.Lock())


def _sse_frame(kind: str, data: dict) -> bytes:
    """Frame one event in SSE wire format (event + data lines, blank-line end)."""
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n".encode()


async def get_history(session: AsyncSession, patient_id: int) -> ChatHistoryResponse:
    """Return the stored conversation, messages, and latest briefing for the UI."""
    conversation = await session.scalar(
        select(Conversation).where(Conversation.patient_id == patient_id)
    )
    messages: list[ChatMessageOut] = []
    if conversation is not None:
        rows = (
            await session.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation.id)
                .order_by(ConversationMessage.id)
            )
        ).all()
        messages = [ChatMessageOut.model_validate(m) for m in rows]

    latest = await session.scalar(
        select(Briefing)
        .where(Briefing.patient_id == patient_id)
        .order_by(Briefing.id.desc())
        .limit(1)
    )
    latest_briefing = (
        BriefingResponse(**latest.content, id=latest.id, generated_at=latest.created_at)
        if latest is not None
        else None
    )
    return ChatHistoryResponse(
        conversation_id=conversation.id if conversation else None,
        messages=messages,
        latest_briefing=latest_briefing,
    )


async def reset_conversation(session: AsyncSession, patient_id: int) -> None:
    """Drop the conversation (messages cascade); the next turn starts fresh.

    The SDK-side transcript file is left behind — harmless, since nothing
    resumes it once the session_id row is gone.
    """
    conversation = await session.scalar(
        select(Conversation).where(Conversation.patient_id == patient_id)
    )
    if conversation is not None:
        await session.delete(conversation)
        await session.commit()
        logger.info("Reset conversation for patient %d", patient_id)


async def stream_chat_turn(
    session: AsyncSession, patient: Patient, message: str
) -> AsyncIterator[bytes]:
    """Run one chat turn and yield SSE frames as the agent works."""
    async with _lock_for(patient.id):
        conversation = await session.scalar(
            select(Conversation).where(Conversation.patient_id == patient.id)
        )
        if conversation is None:
            conversation = Conversation(patient_id=patient.id)
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)

        # Persist the user turn up front so history survives even if the
        # agent errors mid-turn.
        session.add(
            ConversationMessage(
                conversation_id=conversation.id, role="user", content=message
            )
        )
        await session.commit()

        queue: asyncio.Queue[ChatEvent] = asyncio.Queue()
        options = build_chat_options(
            queue, patient.id, conversation.session_id, _serialize_patient(patient)
        )

        async def run_turn() -> None:
            """Producer: drive the agent, then persist and signal completion."""
            try:
                session_id, assistant_text, trace = await drive_chat_turn(
                    message, options, queue
                )
                if session_id:
                    conversation.session_id = session_id
                if assistant_text or trace:
                    session.add(
                        ConversationMessage(
                            conversation_id=conversation.id,
                            role="assistant",
                            content=assistant_text,
                            # Full ordered trace (thinking, tool calls with
                            # results, text) so the UI can replay the agent's
                            # work after a refresh.
                            trace=trace or None,
                        )
                    )
                await session.commit()
                await queue.put(("done", {"session_id": session_id}))
            except BriefingGenerationError as exc:
                logger.exception("Chat turn failed for patient %d", patient.id)
                await queue.put(("error", {"code": exc.code, "message": exc.message}))
            except Exception:
                logger.exception("Unexpected chat error for patient %d", patient.id)
                await queue.put(
                    ("error", {"code": "INTERNAL_ERROR", "message": "Unexpected error"})
                )

        task = asyncio.create_task(run_turn())
        try:
            while True:
                kind, data = await queue.get()
                yield _sse_frame(kind, data)
                if kind in ("done", "error"):
                    break
        finally:
            # Client disconnected mid-turn (or we're done): stop the agent.
            if not task.done():
                task.cancel()
