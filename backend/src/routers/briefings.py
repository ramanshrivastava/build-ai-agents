"""Briefing API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.schemas import BriefingResponse, ErrorDetail
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
        return await generate_briefing(patient)
    except BriefingGenerationError as e:
        logger.exception("Briefing generation failed for patient %d", patient_id)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                code=e.code,
                message=e.message,
            ).model_dump(),
        )
