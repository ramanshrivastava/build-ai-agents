"""Unit tests for briefing_service — mocks at the SDK level."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.models.orm import Patient
from src.services.briefing_service import BriefingGenerationError, generate_briefing

# --- Fixtures ---


@pytest.fixture
def fake_patient() -> Patient:
    """Minimal patient for unit tests (no database needed)."""
    return Patient(
        name="Test Patient",
        date_of_birth=datetime.date(1957, 3, 15),
        gender="F",
        conditions=["Type 2 Diabetes"],
        medications=[
            {"name": "Metformin", "dosage": "500mg", "frequency": "twice daily"}
        ],
        labs=[
            {
                "name": "HbA1c",
                "value": 7.2,
                "unit": "%",
                "date": "2024-01-15",
                "reference_range": {"min": 4.0, "max": 5.6},
            }
        ],
        allergies=["Penicillin"],
        visits=[{"date": "2024-01-15", "reason": "Annual checkup"}],
    )


# Structured output dict matching PatientBriefing schema
VALID_STRUCTURED_OUTPUT = {
    "flags": [
        {
            "category": "labs",
            "severity": "warning",
            "title": "HbA1c elevated",
            "description": "Current HbA1c of 7.2% is above target range",
            "source": "ai",
            "suggested_action": "Consider medication adjustment",
        }
    ],
    "summary": {
        "one_liner": "67-year-old female with Type 2 Diabetes",
        "key_conditions": ["Type 2 Diabetes"],
        "relevant_history": "Patient has been managing diabetes with Metformin.",
    },
    "suggested_actions": [
        {
            "action": "Review HbA1c trend",
            "reason": "Current value above target",
            "priority": 1,
        }
    ],
}


# --- Helpers ---


def _make_result_message(*, structured_output=None, is_error=False, result=None):
    """Create a mock ResultMessage with the given fields."""
    msg = AsyncMock()
    msg.structured_output = structured_output
    msg.is_error = is_error
    msg.result = result
    # Make isinstance(msg, ResultMessage) return True
    msg.__class__ = _get_result_message_class()
    return msg


def _get_result_message_class():
    from claude_agent_sdk import ResultMessage

    return ResultMessage


async def _async_iter(items):
    """Async generator that yields each item."""
    for item in items:
        yield item


# --- Tests ---


@patch("src.services.briefing_service.query")
async def test_generate_briefing_success(mock_query, fake_patient):
    """Happy path: valid structured output → BriefingResponse."""
    msg = _make_result_message(structured_output=VALID_STRUCTURED_OUTPUT)
    mock_query.return_value = _async_iter([msg])

    result = await generate_briefing(fake_patient)

    assert len(result.flags) == 1
    assert result.flags[0].title == "HbA1c elevated"
    assert result.flags[0].category == "labs"
    assert result.summary.one_liner == "67-year-old female with Type 2 Diabetes"
    assert len(result.suggested_actions) == 1
    assert result.generated_at is not None


@patch("src.services.briefing_service.query")
async def test_generate_briefing_agent_error(mock_query, fake_patient):
    """Agent returns is_error=True → BriefingGenerationError(AGENT_ERROR)."""
    msg = _make_result_message(is_error=True, result="Model refused to answer")
    mock_query.return_value = _async_iter([msg])

    with pytest.raises(BriefingGenerationError) as exc_info:
        await generate_briefing(fake_patient)

    assert exc_info.value.code == "AGENT_ERROR"
    assert "Model refused to answer" in exc_info.value.message


@patch("src.services.briefing_service.query")
async def test_generate_briefing_no_result(mock_query, fake_patient):
    """No ResultMessage yielded → BriefingGenerationError(NO_RESULT)."""
    # Yield nothing — simulates agent producing no result
    mock_query.return_value = _async_iter([])

    with pytest.raises(BriefingGenerationError) as exc_info:
        await generate_briefing(fake_patient)

    assert exc_info.value.code == "NO_RESULT"


@patch("src.services.briefing_service.query")
async def test_generate_briefing_cli_not_found(mock_query, fake_patient):
    """CLINotFoundError → BriefingGenerationError(CLI_NOT_FOUND)."""
    from claude_agent_sdk import CLINotFoundError

    mock_query.side_effect = CLINotFoundError()

    with pytest.raises(BriefingGenerationError) as exc_info:
        await generate_briefing(fake_patient)

    assert exc_info.value.code == "CLI_NOT_FOUND"
