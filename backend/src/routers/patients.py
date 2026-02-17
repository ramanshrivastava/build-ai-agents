"""Patient API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.schemas import ErrorDetail, PatientResponse
from src.services.patient_service import get_all_patients, get_patient_by_id

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


@router.get("", response_model=list[PatientResponse])
async def list_patients(
    session: AsyncSession = Depends(get_session),
) -> list[PatientResponse]:
    patients = await get_all_patients(session)
    return [PatientResponse.model_validate(p) for p in patients]


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: int,
    session: AsyncSession = Depends(get_session),
) -> PatientResponse:
    patient = await get_patient_by_id(session, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="PATIENT_NOT_FOUND",
                message=f"Patient with ID {patient_id} not found",
            ).model_dump(),
        )
    return PatientResponse.model_validate(patient)
