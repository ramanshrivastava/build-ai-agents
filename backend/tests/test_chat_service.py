"""Unit tests for chat_service — mocks the agent turn at drive_chat_turn."""

from __future__ import annotations

import asyncio

from typing import NoReturn

import pytest

from claude_agent_sdk import ClaudeAgentOptions
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agents.chat_agent import ChatEvent
from src.models.orm import Patient
from src.services.briefing_service import BriefingGenerationError
from src.services.chat_service import stream_chat_turn

KEY = "sk-ant-usr-FAKE_unit-test-key-0000"


async def _failing_turn(
    prompt: str, options: ClaudeAgentOptions, queue: asyncio.Queue[ChatEvent]
) -> NoReturn:
    raise BriefingGenerationError(
        code="AGENT_ERROR", message=f"401 invalid x-api-key {KEY}"
    )


async def _run_failing_turn(
    patient: Patient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """Drive one chat turn whose agent fails with key material in the error."""
    monkeypatch.setattr("src.agents.chat_agent.settings.anthropic_api_key", KEY)
    monkeypatch.setattr("src.services.chat_service.drive_chat_turn", _failing_turn)
    async with session_factory() as session:
        return [
            frame.decode()
            async for frame in stream_chat_turn(session, patient, "hello")
        ]


async def test_error_event_masks_key_material(
    seed_patient: Patient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BriefingGenerationError messages can quote CLI/model output, so the SSE
    error event scrubs key material like every other event."""
    frames = await _run_failing_turn(seed_patient, session_factory, monkeypatch)

    assert frames[-1].startswith("event: error\n")
    assert KEY not in frames[-1]
    assert "sk-ant-<redacted>" in frames[-1]


async def test_error_log_masks_key_material(
    seed_patient: Patient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The server log for a failed turn carries the code and the masked
    message — no raw message, and no traceback (whose text repeats it)."""
    await _run_failing_turn(seed_patient, session_factory, monkeypatch)

    assert KEY not in caplog.text
    assert "AGENT_ERROR" in caplog.text
    assert "sk-ant-<redacted>" in caplog.text
