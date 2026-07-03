"""Unit tests for chat_agent — mocks at the ClaudeSDKClient level."""

from __future__ import annotations

import asyncio
import datetime

from unittest.mock import patch

import pytest

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)
from sqlalchemy import select

from src.agents.chat_agent import (
    AGENT_HOME,
    build_chat_options,
    drive_chat_turn,
    make_publish_tool,
)
from src.models.orm import Briefing, Patient
from src.services.briefing_service import BriefingGenerationError
from tests.test_briefing_agent import VALID_STRUCTURED_OUTPUT

# --- Helpers ---


def _result(session_id: str = "s-1", *, is_error: bool = False, result: str | None = None):
    return ResultMessage(
        subtype="success" if not is_error else "error",
        duration_ms=1000,
        duration_api_ms=800,
        is_error=is_error,
        num_turns=1,
        session_id=session_id,
        total_cost_usd=0.01,
        result=result,
    )


class FakeClient:
    """Stands in for ClaudeSDKClient: records the options and the prompt,
    then replays a canned message stream."""

    last_options = None
    last_prompt = None
    messages: list = []

    def __init__(self, options):
        FakeClient.last_options = options

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def query(self, prompt):
        FakeClient.last_prompt = prompt

    async def receive_response(self):
        for message in FakeClient.messages:
            yield message


# --- drive_chat_turn ---


@patch("src.agents.chat_agent.ClaudeSDKClient", FakeClient)
async def test_drive_chat_turn_events_and_session():
    """SDK messages map to SSE events in order; session_id is captured."""
    FakeClient.messages = [
        SystemMessage(subtype="init", data={"session_id": "s-init"}),
        AssistantMessage(
            content=[
                TextBlock(text="Let me check."),
                ToolUseBlock(
                    id="t1",
                    name="mcp__guidelines__search_clinical_guidelines",
                    input={"query": "metformin renal dosing"},
                ),
            ],
            model="test-model",
        ),
        AssistantMessage(content=[TextBlock(text="All done.")], model="test-model"),
        _result("s-init"),
    ]
    queue: asyncio.Queue = asyncio.Queue()
    options = build_chat_options(queue, patient_id=1, resume_session_id=None, patient_json="{}")

    session_id, text = await drive_chat_turn("hello", options, queue)

    assert session_id == "s-init"
    assert text == "Let me check.All done."
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert events == [
        ("text", {"text": "Let me check."}),
        (
            "tool_use",
            {
                "tool": "search_clinical_guidelines",
                "input": {"query": "metformin renal dosing"},
            },
        ),
        ("text", {"text": "All done."}),
    ]


@patch("src.agents.chat_agent.ClaudeSDKClient", FakeClient)
async def test_publish_briefing_input_suppressed():
    """publish_briefing's tool_use input (the whole briefing) is not re-streamed."""
    FakeClient.messages = [
        AssistantMessage(
            content=[
                ToolUseBlock(
                    id="t1",
                    name="mcp__publisher__publish_briefing",
                    input=VALID_STRUCTURED_OUTPUT,
                )
            ],
            model="test-model",
        ),
        _result(),
    ]
    queue: asyncio.Queue = asyncio.Queue()
    options = build_chat_options(queue, 1, None, "{}")

    await drive_chat_turn("/briefing", options, queue)

    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert events == [("tool_use", {"tool": "publish_briefing", "input": {}})]


@patch("src.agents.chat_agent.ClaudeSDKClient", FakeClient)
async def test_error_result_raises():
    FakeClient.messages = [_result(is_error=True, result="model exploded")]
    queue: asyncio.Queue = asyncio.Queue()
    options = build_chat_options(queue, 1, None, "{}")

    with pytest.raises(BriefingGenerationError) as exc_info:
        await drive_chat_turn("hello", options, queue)
    assert exc_info.value.code == "AGENT_ERROR"


@patch("src.agents.chat_agent.ClaudeSDKClient", FakeClient)
async def test_empty_stream_raises_no_result():
    FakeClient.messages = []
    queue: asyncio.Queue = asyncio.Queue()
    options = build_chat_options(queue, 1, None, "{}")

    with pytest.raises(BriefingGenerationError) as exc_info:
        await drive_chat_turn("hello", options, queue)
    assert exc_info.value.code == "NO_RESULT"


# --- build_chat_options ---


def test_build_chat_options_wiring():
    queue: asyncio.Queue = asyncio.Queue()
    options = build_chat_options(queue, 1, "s-resume", '{"name": "Maria"}')

    assert options.resume == "s-resume"
    assert options.max_turns == 12
    assert options.cwd == str(AGENT_HOME)
    assert options.setting_sources == ["project"]
    assert set(options.mcp_servers) == {"guidelines", "publisher"}
    assert options.allowed_tools == [
        "Skill",
        "mcp__guidelines__search_clinical_guidelines",
        "mcp__publisher__publish_briefing",
    ]
    # Patient record rides in the system prompt so user messages stay verbatim
    # (a leading prefix would break "/briefing" slash-command detection).
    assert '{"name": "Maria"}' in options.system_prompt


def test_build_chat_options_first_turn_no_resume():
    options = build_chat_options(asyncio.Queue(), 1, None, "{}")
    assert options.resume is None


# --- publish_briefing tool handler ---


@pytest.fixture
async def db_patient(session_factory) -> Patient:
    async with session_factory() as session:
        patient = Patient(
            name="Maria Garcia",
            date_of_birth=datetime.date(1957, 3, 15),
            gender="F",
            conditions=["Type 2 Diabetes"],
        )
        session.add(patient)
        await session.commit()
        await session.refresh(patient)
        return patient


async def test_publish_tool_persists_and_queues(monkeypatch, session_factory, db_patient):
    monkeypatch.setattr("src.database.async_session", session_factory)
    queue: asyncio.Queue = asyncio.Queue()
    publish = make_publish_tool(queue, db_patient.id)

    response = await publish.handler(dict(VALID_STRUCTURED_OUTPUT))

    assert "isError" not in response
    kind, payload = queue.get_nowait()
    assert kind == "briefing_published"
    assert payload["id"] is not None
    assert len(payload["flags"]) == len(VALID_STRUCTURED_OUTPUT["flags"])
    async with session_factory() as session:
        stored = (await session.scalars(select(Briefing))).all()
    assert len(stored) == 1
    assert stored[0].patient_id == db_patient.id


async def test_publish_tool_rejects_invalid_payload(monkeypatch, session_factory):
    monkeypatch.setattr("src.database.async_session", session_factory)
    queue: asyncio.Queue = asyncio.Queue()
    publish = make_publish_tool(queue, 1)

    response = await publish.handler({"flags": "not-a-list"})

    assert response["isError"] is True
    assert queue.empty()
    async with session_factory() as session:
        assert (await session.scalars(select(Briefing))).all() == []
