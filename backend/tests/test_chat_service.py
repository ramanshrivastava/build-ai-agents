"""Unit tests for chat_service — mocks the agent turn at drive_chat_turn."""

from __future__ import annotations

import pytest

from src.services.briefing_service import BriefingGenerationError
from src.services.chat_service import stream_chat_turn


async def test_error_event_masks_key_material(
    seed_patient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BriefingGenerationError messages can quote CLI/model output, so the SSE
    error event scrubs key material like every other event."""
    key = "sk-ant-usr-FAKE_unit-test-key-0000"
    monkeypatch.setattr("src.agents.chat_agent.settings.anthropic_api_key", key)

    async def failing_turn(prompt, options, queue):
        raise BriefingGenerationError(
            code="AGENT_ERROR", message=f"401 invalid x-api-key {key}"
        )

    monkeypatch.setattr("src.services.chat_service.drive_chat_turn", failing_turn)

    async with session_factory() as session:
        frames = [
            frame.decode()
            async for frame in stream_chat_turn(session, seed_patient, "hello")
        ]

    assert frames[-1].startswith("event: error\n")
    assert key not in frames[-1]
    assert "sk-ant-<redacted>" in frames[-1]
