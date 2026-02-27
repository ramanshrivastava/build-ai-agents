"""Unit tests for briefing_agent — mocks at the SDK level."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.models.orm import Patient
from src.agents.briefing_agent import BriefingGenerationError, generate_briefing

# --- Fixtures ---


@pytest.fixture
def fake_patient() -> Patient:
    """Minimal patient for unit tests (no database needed)."""
    return Patient(
        name="Maria Garcia",
        date_of_birth=datetime.date(1957, 3, 15),
        gender="F",
        conditions=["Type 2 Diabetes", "Hypertension", "CKD Stage 3"],
        medications=[
            {"name": "Metformin", "dosage": "1000mg", "frequency": "twice daily"},
            {"name": "Lisinopril", "dosage": "20mg", "frequency": "once daily"},
        ],
        labs=[
            {
                "name": "HbA1c",
                "value": 7.2,
                "unit": "%",
                "date": "2024-01-15",
                "reference_range": {"min": 4.0, "max": 5.6},
            },
            {
                "name": "eGFR",
                "value": 45,
                "unit": "mL/min/1.73m2",
                "date": "2024-01-15",
                "reference_range": {"min": 60, "max": 120},
            },
        ],
        allergies=["Penicillin"],
        visits=[{"date": "2024-01-15", "reason": "Diabetes follow-up"}],
    )


# Structured output matching PatientBriefing schema (with citations)
VALID_STRUCTURED_OUTPUT = {
    "flags": [
        {
            "category": "labs",
            "severity": "warning",
            "title": "HbA1c above target",
            "description": "HbA1c of 7.2% is above the recommended target of <7.0% [1]",
            "source": "ai",
            "suggested_action": "Consider medication adjustment per diabetes guidelines [1]",
        },
        {
            "category": "medications",
            "severity": "warning",
            "title": "Metformin dose review needed",
            "description": "With eGFR of 45, metformin max dose should be 1000mg/day [2]",
            "source": "ai",
            "suggested_action": "Verify current dosing aligns with renal guidelines [2]",
        },
    ],
    "summary": {
        "one_liner": "67-year-old female with diabetes, hypertension, and CKD Stage 3",
        "key_conditions": ["Type 2 Diabetes", "Hypertension", "CKD Stage 3"],
        "relevant_history": "Patient on metformin and lisinopril with declining renal function.",
    },
    "suggested_actions": [
        {
            "action": "Review metformin dosing given eGFR 45",
            "reason": "Guidelines recommend max 1000mg/day at this eGFR [2]",
            "priority": 1,
        },
        {
            "action": "Monitor potassium levels",
            "reason": "CKD + ACE inhibitor increases hyperkalemia risk [3]",
            "priority": 2,
        },
    ],
}


# --- Helpers ---


def _make_result_message(*, structured_output=None, is_error=False, result=None):
    """Create a mock ResultMessage."""
    msg = AsyncMock()
    msg.structured_output = structured_output
    msg.is_error = is_error
    msg.result = result
    msg.__class__ = _get_result_message_class()
    return msg


def _get_result_message_class():
    from claude_agent_sdk import ResultMessage

    return ResultMessage


async def _async_iter(items):
    for item in items:
        yield item


# --- Tests ---


@patch("src.agents.briefing_agent.query")
async def test_generate_briefing_success(mock_query, fake_patient):
    """Happy path: agent returns structured briefing with citations."""
    msg = _make_result_message(structured_output=VALID_STRUCTURED_OUTPUT)
    mock_query.return_value = _async_iter([msg])

    result = await generate_briefing(fake_patient)

    assert len(result.flags) == 2
    assert "[1]" in result.flags[0].description
    assert result.summary.one_liner
    assert len(result.suggested_actions) == 2
    assert result.generated_at is not None


@patch("src.agents.briefing_agent.query")
async def test_generate_briefing_uses_mcp_server(mock_query, fake_patient):
    """Verify the agent is configured with MCP tools and max_turns=4."""
    msg = _make_result_message(structured_output=VALID_STRUCTURED_OUTPUT)
    mock_query.return_value = _async_iter([msg])

    await generate_briefing(fake_patient)

    call_kwargs = mock_query.call_args
    options = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options")
    assert options.max_turns == 4
    assert "briefing" in options.mcp_servers
    assert "mcp__briefing__search_clinical_guidelines" in options.allowed_tools


@patch("src.agents.briefing_agent.query")
async def test_generate_briefing_agent_error(mock_query, fake_patient):
    """Agent returns error → BriefingGenerationError."""
    msg = _make_result_message(is_error=True, result="Tool call failed")
    mock_query.return_value = _async_iter([msg])

    with pytest.raises(BriefingGenerationError) as exc_info:
        await generate_briefing(fake_patient)

    assert exc_info.value.code == "AGENT_ERROR"


@patch("src.agents.briefing_agent.query")
async def test_generate_briefing_no_result(mock_query, fake_patient):
    """No ResultMessage → BriefingGenerationError(NO_RESULT)."""
    mock_query.return_value = _async_iter([])

    with pytest.raises(BriefingGenerationError) as exc_info:
        await generate_briefing(fake_patient)

    assert exc_info.value.code == "NO_RESULT"


@patch("src.agents.briefing_agent.query")
async def test_generate_briefing_cli_not_found(mock_query, fake_patient):
    """CLINotFoundError → BriefingGenerationError."""
    from claude_agent_sdk import CLINotFoundError

    mock_query.side_effect = CLINotFoundError()

    with pytest.raises(BriefingGenerationError) as exc_info:
        await generate_briefing(fake_patient)

    assert exc_info.value.code == "CLI_NOT_FOUND"
