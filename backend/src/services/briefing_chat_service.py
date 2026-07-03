"""Conversational follow-up over a persisted briefing."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.briefing_agent import answer_followup_question
from src.models.orm import Briefing, BriefingMessage, Patient
from src.models.schemas import BriefingChatMessage, BriefingChatResponse
from src.services.briefing_service import BriefingGenerationError

logger = logging.getLogger(__name__)


async def store_briefing(
    session: AsyncSession, patient_id: int, content: dict
) -> Briefing:
    """Persist a generated briefing so follow-up questions can reference it."""
    briefing = Briefing(patient_id=patient_id, content=content)
    session.add(briefing)
    await session.commit()
    await session.refresh(briefing)
    logger.info("Stored briefing %d for patient %d", briefing.id, patient_id)
    return briefing


async def answer_followup(
    session: AsyncSession,
    patient: Patient,
    briefing_id: int,
    question: str,
) -> BriefingChatResponse:
    """Answer a clinician's follow-up about an existing briefing.

    Loads the stored briefing + prior Q&A, asks the agent (free-text, with the
    RAG tool available), then persists the new question/answer pair.
    """
    briefing = await session.get(Briefing, briefing_id)
    if briefing is None or briefing.patient_id != patient.id:
        raise BriefingGenerationError(
            code="BRIEFING_NOT_FOUND",
            message=(
                f"Briefing {briefing_id} for patient {patient.id} not found. "
                "Generate a briefing via POST /{{id}}/briefing first."
            ),
        )

    prior_msgs = (
        await session.scalars(
            select(BriefingMessage)
            .where(BriefingMessage.briefing_id == briefing_id)
            .order_by(BriefingMessage.id)
        )
    ).all()
    history = [(m.role, m.content) for m in prior_msgs]

    try:
        answer = await answer_followup_question(
            patient, briefing.content, history, question
        )
    except BriefingGenerationError:
        raise

    session.add(BriefingMessage(briefing_id=briefing_id, role="user", content=question))
    session.add(
        BriefingMessage(briefing_id=briefing_id, role="assistant", content=answer)
    )
    await session.commit()

    all_msgs = (
        await session.scalars(
            select(BriefingMessage)
            .where(BriefingMessage.briefing_id == briefing_id)
            .order_by(BriefingMessage.id)
        )
    ).all()
    return BriefingChatResponse(
        briefing_id=briefing_id,
        answer=answer,
        history=[BriefingChatMessage.model_validate(m) for m in all_msgs],
    )
