"""Briefing endpoint tests."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

from httpx import AsyncClient

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
