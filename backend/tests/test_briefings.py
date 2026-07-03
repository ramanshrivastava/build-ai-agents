"""Briefing endpoint tests."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

from httpx import AsyncClient
from sqlalchemy import select

from src.models.orm import Briefing
from src.models.schemas import BriefingResponse, Flag, SuggestedAction, Summary
from src.services.briefing_service import BriefingGenerationError

MOCK_BRIEFING = BriefingResponse(
    flags=[
        Flag(
            category="labs",
            severity="warning",
            title="HbA1c elevated",
            description="Current HbA1c of 7.2% is above target range",
            source="ai",
            suggested_action="Consider medication adjustment",
        )
    ],
    summary=Summary(
        one_liner="67-year-old female with Type 2 Diabetes",
        key_conditions=["Type 2 Diabetes"],
        relevant_history="Patient has been managing diabetes with Metformin.",
    ),
    suggested_actions=[
        SuggestedAction(
            action="Review HbA1c trend",
            reason="Current value above target",
            priority=1,
        )
    ],
    generated_at=datetime.datetime(2024, 1, 15, 12, 0, 0, tzinfo=datetime.UTC),
)


async def test_create_briefing_success(
    client: AsyncClient, seed_patient, mocker
) -> None:
    mocker.patch(
        "src.routers.briefings.generate_briefing",
        new_callable=AsyncMock,
        return_value=MOCK_BRIEFING,
    )
    response = await client.post(f"/api/v1/patients/{seed_patient.id}/briefing")
    assert response.status_code == 200
    data = response.json()
    assert "flags" in data
    assert "summary" in data
    assert "suggested_actions" in data
    assert "generated_at" in data
    assert len(data["flags"]) == 1
    assert data["flags"][0]["title"] == "HbA1c elevated"


async def test_create_briefing_patient_not_found(client: AsyncClient) -> None:
    response = await client.post("/api/v1/patients/999/briefing")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "PATIENT_NOT_FOUND"


async def test_create_briefing_agent_error(
    client: AsyncClient, seed_patient, mocker
) -> None:
    mocker.patch(
        "src.routers.briefings.generate_briefing",
        new_callable=AsyncMock,
        side_effect=BriefingGenerationError(
            code="CLI_NOT_FOUND", message="Claude CLI not found"
        ),
    )
    response = await client.post(f"/api/v1/patients/{seed_patient.id}/briefing")
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "CLI_NOT_FOUND"


async def test_managed_briefing_503_when_proxy_configured(
    client: AsyncClient, seed_patient, monkeypatch
) -> None:
    """Managed Agents is server-hosted by Anthropic and can't run through a
    translation proxy (Gemini/etc.) — fail clearly rather than misroute."""
    monkeypatch.setattr(
        "src.config.settings.anthropic_base_url", "http://localhost:4000"
    )
    response = await client.post(f"/api/v1/patients/{seed_patient.id}/briefing/managed")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MANAGED_AGENTS_PROXY_INCOMPATIBLE"


# --- Conversational follow-up (Workstream B) ---


async def _make_briefing(session_factory, patient_id: int) -> int:
    """Insert a persisted briefing directly and return its id."""
    async with session_factory() as s:
        briefing = Briefing(
            patient_id=patient_id,
            content={
                "summary": {
                    "one_liner": "test",
                    "key_conditions": [],
                    "relevant_history": "",
                }
            },
        )
        s.add(briefing)
        await s.commit()
        await s.refresh(briefing)
        return briefing.id


async def test_create_briefing_persists_and_returns_id(
    client: AsyncClient, seed_patient, session_factory, mocker
) -> None:
    """POST /briefing stores the briefing and returns its id for follow-up chat."""
    mocker.patch(
        "src.routers.briefings.generate_briefing",
        new_callable=AsyncMock,
        return_value=MOCK_BRIEFING,
    )
    response = await client.post(f"/api/v1/patients/{seed_patient.id}/briefing")
    assert response.status_code == 200
    assert response.json()["id"] is not None

    async with session_factory() as s:
        rows = (
            await s.scalars(
                select(Briefing).where(Briefing.patient_id == seed_patient.id)
            )
        ).all()
    assert len(rows) == 1


async def test_chat_about_briefing_success(
    client: AsyncClient, seed_patient, session_factory, mocker
) -> None:
    """A follow-up question returns the agent answer plus the new Q&A turn."""
    briefing_id = await _make_briefing(session_factory, seed_patient.id)
    mocker.patch(
        "src.services.briefing_chat_service.answer_followup_question",
        new_callable=AsyncMock,
        return_value="Because eGFR is 45, metformin should be capped [1].",
    )

    response = await client.post(
        f"/api/v1/patients/{seed_patient.id}/briefing/{briefing_id}/chat",
        json={"question": "Why was metformin flagged?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["briefing_id"] == briefing_id
    assert "eGFR" in data["answer"]
    roles = [m["role"] for m in data["history"]]
    assert roles == ["user", "assistant"]
    assert data["history"][0]["content"] == "Why was metformin flagged?"


async def test_chat_about_briefing_not_found(client: AsyncClient, seed_patient) -> None:
    """Following up on a nonexistent briefing returns 404 BRIEFING_NOT_FOUND."""
    response = await client.post(
        f"/api/v1/patients/{seed_patient.id}/briefing/9999/chat",
        json={"question": "anything"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "BRIEFING_NOT_FOUND"


async def test_chat_replays_prior_turns_as_history(
    client: AsyncClient, seed_patient, session_factory, mocker
) -> None:
    """The second follow-up sees the first Q&A in its history (true multi-turn)."""
    briefing_id = await _make_briefing(session_factory, seed_patient.id)
    mock_agent = mocker.patch(
        "src.services.briefing_chat_service.answer_followup_question",
        new_callable=AsyncMock,
        return_value="A1",
    )

    await client.post(
        f"/api/v1/patients/{seed_patient.id}/briefing/{briefing_id}/chat",
        json={"question": "Q1"},
    )
    await client.post(
        f"/api/v1/patients/{seed_patient.id}/briefing/{briefing_id}/chat",
        json={"question": "Q2"},
    )

    assert mock_agent.await_count == 2
    # answer_followup_question(patient, content, history, question) -> history is args[2]
    second_history = mock_agent.call_args_list[1].args[2]
    assert ("user", "Q1") in second_history
    assert ("assistant", "A1") in second_history
