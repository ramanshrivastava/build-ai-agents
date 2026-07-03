"""Briefing API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_session
from src.models.schemas import (
    BriefingChatRequest,
    BriefingChatResponse,
    BriefingResponse,
    ErrorDetail,
)
from src.services.managed_briefing_service import (
    generate_managed_briefing,
    reset_managed_session,
)
from src.agents.briefing_agent import generate_briefing_via_http_mcp
from src.services.briefing_chat_service import answer_followup, store_briefing
from src.services.briefing_service import BriefingGenerationError, generate_briefing
from src.services.patient_service import get_patient_by_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/patients", tags=["briefings"])


@router.post("/{patient_id}/briefing", response_model=BriefingResponse)
async def create_briefing(
    patient_id: int,
    session: AsyncSession = Depends(get_session),
) -> BriefingResponse:
    patient = await get_patient_by_id(session, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="PATIENT_NOT_FOUND",
                message=f"Patient with ID {patient_id} not found",
            ).model_dump(),
        )

    logger.info("Generating briefing for patient %d", patient_id)
    try:
        response = await generate_briefing(patient)
    except BriefingGenerationError as e:
        logger.exception("Briefing generation failed for patient %d", patient_id)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                code=e.code,
                message=e.message,
            ).model_dump(),
        )
    # Persist so follow-up chat (POST /{id}/briefing/{briefing_id}/chat) can
    # reference it without regenerating.
    stored = await store_briefing(session, patient_id, response.model_dump(mode="json"))
    response.id = stored.id
    return response


@router.post(
    "/{patient_id}/briefing/{briefing_id}/chat",
    response_model=BriefingChatResponse,
)
async def chat_about_briefing(
    patient_id: int,
    briefing_id: int,
    body: BriefingChatRequest,
    session: AsyncSession = Depends(get_session),
) -> BriefingChatResponse:
    """Ask a follow-up question about a previously generated briefing.

    Multi-turn: prior questions/answers are replayed as context. Requires the
    briefing to have been generated (and persisted) via POST /{id}/briefing.
    Runs on the same model/route as briefing generation (Gemini via proxy if
    ANTHROPIC_BASE_URL is set).
    """
    patient = await get_patient_by_id(session, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="PATIENT_NOT_FOUND",
                message=f"Patient with ID {patient_id} not found",
            ).model_dump(),
        )

    logger.info("Follow-up chat for patient %d, briefing %d", patient_id, briefing_id)
    try:
        return await answer_followup(session, patient, briefing_id, body.question)
    except BriefingGenerationError as e:
        status_code = 404 if e.code == "BRIEFING_NOT_FOUND" else 500
        logger.exception("Follow-up chat failed for briefing %d", briefing_id)
        raise HTTPException(
            status_code=status_code,
            detail=ErrorDetail(code=e.code, message=e.message).model_dump(),
        ) from e


@router.post("/{patient_id}/briefing/external-mcp", response_model=BriefingResponse)
async def create_external_mcp_briefing(
    patient_id: int,
    session: AsyncSession = Depends(get_session),
) -> BriefingResponse:
    """Generate a briefing where the search tool is served by an external HTTP MCP server.

    Requires the standalone FastMCP server (`mcp_server/server.py`) to be running at
    EXTERNAL_MCP_URL. The agent reaches the tool over Streamable HTTP rather than in-process.
    """
    patient = await get_patient_by_id(session, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="PATIENT_NOT_FOUND",
                message=f"Patient with ID {patient_id} not found",
            ).model_dump(),
        )

    logger.info("Generating external-MCP briefing for patient %d", patient_id)
    try:
        return await generate_briefing_via_http_mcp(patient)
    except BriefingGenerationError as e:
        logger.exception(
            "External-MCP briefing generation failed for patient %d", patient_id
        )
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(code=e.code, message=e.message).model_dump(),
        ) from e


@router.post("/{patient_id}/briefing/managed", response_model=BriefingResponse)
async def create_managed_briefing(
    patient_id: int,
    session: AsyncSession = Depends(get_session),
) -> BriefingResponse:
    patient = await get_patient_by_id(session, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="PATIENT_NOT_FOUND",
                message=f"Patient with ID {patient_id} not found",
            ).model_dump(),
        )

    logger.info("Generating managed-agent briefing for patient %d", patient_id)
    if settings.anthropic_base_url:
        # Managed Agents is server-hosted by Anthropic and cannot be re-pointed
        # through the configured translation proxy (Gemini/etc.). Fail clearly
        # rather than silently hitting real Anthropic or the wrong endpoint.
        raise HTTPException(
            status_code=503,
            detail=ErrorDetail(
                code="MANAGED_AGENTS_PROXY_INCOMPATIBLE",
                message=(
                    "Managed Agents cannot run through the configured "
                    "ANTHROPIC_BASE_URL proxy; it is server-hosted by Anthropic. "
                    "Use the in-process or HTTP-MCP briefing endpoint instead."
                ),
            ).model_dump(),
        )
    try:
        return await generate_managed_briefing(session, patient)
    except BriefingGenerationError as e:
        logger.exception(
            "Managed briefing generation failed for patient %d",
            patient_id,
        )
        status_code = {
            "MANAGED_AGENTS_NOT_CONFIGURED": 503,
            "MANAGED_AGENTS_API_ERROR": 502,
            "MANAGED_AGENTS_TIMEOUT": 504,
            "MANAGED_AGENTS_INVALID_OUTPUT": 500,
        }.get(e.code, 500)
        raise HTTPException(
            status_code=status_code,
            detail=ErrorDetail(code=e.code, message=e.message).model_dump(),
        ) from e


@router.delete("/{patient_id}/briefing/managed/session", status_code=204)
async def delete_managed_briefing_session(
    patient_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    patient = await get_patient_by_id(session, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="PATIENT_NOT_FOUND",
                message=f"Patient with ID {patient_id} not found",
            ).model_dump(),
        )

    await reset_managed_session(session, patient_id)
