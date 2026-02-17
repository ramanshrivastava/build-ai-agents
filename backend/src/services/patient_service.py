"""Patient data access service."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import Patient


async def get_all_patients(session: AsyncSession) -> Sequence[Patient]:
    result = await session.execute(select(Patient).order_by(Patient.id))
    return result.scalars().all()


async def get_patient_by_id(session: AsyncSession, patient_id: int) -> Patient | None:
    result = await session.execute(select(Patient).where(Patient.id == patient_id))
    return result.scalar_one_or_none()
