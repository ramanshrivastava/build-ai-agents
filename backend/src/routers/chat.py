"""Unified patient chat endpoints (SSE streaming).

POST streams the agent's work as Server-Sent Events over a regular HTTP
response — no WebSocket needed, because chat is one-directional while a turn
runs. Note the response is a StreamingResponse even though the route is POST:
the browser consumes it with fetch + ReadableStream (EventSource only
supports GET).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.orm import Patient
from src.models.schemas import ChatHistoryResponse, ChatRequest, ErrorDetail
from src.services.chat_service import (
    get_history,
    reset_conversation,
    stream_chat_turn,
)
from src.services.patient_service import get_patient_by_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/patients", tags=["chat"])


async def _require_patient(session: AsyncSession, patient_id: int) -> Patient:
    patient = await get_patient_by_id(session, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="PATIENT_NOT_FOUND",
                message=f"Patient with ID {patient_id} not found",
            ).model_dump(),
        )
    return patient


@router.post("/{patient_id}/chat")
async def chat(
    patient_id: int,
    request: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Run one chat turn, streaming SSE events as the agent works.

    Event vocabulary (the contract with the frontend): text, tool_use,
    tool_result, briefing_published, done, error.
    """
    patient = await _require_patient(session, patient_id)
    logger.info("Chat turn for patient %d", patient_id)
    return StreamingResponse(
        stream_chat_turn(session, patient, request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tell proxies (nginx & co.) not to buffer — SSE must flush live.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{patient_id}/chat", response_model=ChatHistoryResponse)
async def chat_history(
    patient_id: int,
    session: AsyncSession = Depends(get_session),
) -> ChatHistoryResponse:
    await _require_patient(session, patient_id)
    return await get_history(session, patient_id)


@router.delete("/{patient_id}/chat", status_code=204)
async def reset_chat(
    patient_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Start over: drop the conversation so the next turn opens a new session."""
    await _require_patient(session, patient_id)
    await reset_conversation(session, patient_id)
