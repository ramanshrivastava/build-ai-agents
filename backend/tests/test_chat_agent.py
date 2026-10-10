"""Unit tests for chat_agent — mocks at the ClaudeSDKClient level."""

from __future__ import annotations

import asyncio
import datetime
import json

from unittest.mock import patch

import pytest

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


def _result(
    session_id: str = "s-1", *, is_error: bool = False, result: str | None = None
):
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
async def test_drive_chat_turn_events_session_and_trace():
    """SDK messages map to SSE events in order; session_id and trace captured."""
    FakeClient.messages = [
        SystemMessage(subtype="init", data={"session_id": "s-init"}),
        AssistantMessage(
            content=[
                ThinkingBlock(thinking="Reviewing labs.", signature="sig"),
                TextBlock(text="Let me check."),
                ToolUseBlock(
                    id="t1",
                    name="mcp__guidelines__search_clinical_guidelines",
                    input={"query": "metformin renal dosing"},
                ),
            ],
            model="test-model",
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="t1",
                    content=[{"type": "text", "text": "guideline excerpt"}],
                    is_error=False,
                )
            ]
        ),
        AssistantMessage(content=[TextBlock(text="All done.")], model="test-model"),
        _result("s-init"),
    ]
    queue: asyncio.Queue = asyncio.Queue()
    options = build_chat_options(
        queue, patient_id=1, resume_session_id=None, patient_json="{}"
    )

    session_id, text, trace = await drive_chat_turn("hello", options, queue)

    assert session_id == "s-init"
    assert text == "Let me check.All done."
    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert events == [
        ("thinking", {"text": "Reviewing labs."}),
        ("text", {"text": "Let me check."}),
        (
            "tool_use",
            {
                "id": "t1",
                "tool": "search_clinical_guidelines",
                "input": {"query": "metformin renal dosing"},
            },
        ),
        (
            "tool_result",
            {"tool_use_id": "t1", "is_error": False, "content": "guideline excerpt"},
        ),
        ("text", {"text": "All done."}),
    ]
    # The persisted trace interleaves parts in order, with the tool result
    # attached to its originating call.
    assert [p["type"] for p in trace] == ["thinking", "text", "tool_use", "text"]
    assert trace[2]["result"] == {"is_error": False, "content": "guideline excerpt"}


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
    assert events == [
        ("tool_use", {"id": "t1", "tool": "publish_briefing", "input": {}})
    ]


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


def test_build_chat_options_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pin: the real backend/.env may carry a key; this test asserts the
    # web-tools-disabled baseline.
    monkeypatch.setattr("src.agents.chat_agent.settings.firecrawl_api_key", "")
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


def test_build_chat_options_first_turn_no_resume() -> None:
    options = build_chat_options(asyncio.Queue(), 1, None, "{}")
    assert options.resume is None


def test_build_chat_options_web_tools_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a Firecrawl key: Bash allowed, key injected into subprocess env."""
    monkeypatch.setattr(
        "src.agents.chat_agent.settings.firecrawl_api_key", "fc-unit-test-key"
    )
    options = build_chat_options(asyncio.Queue(), 1, None, "{}")

    assert "Bash" in options.allowed_tools
    assert options.env["FIRECRAWL_API_KEY"] == "fc-unit-test-key"
    # Env delivery, not permission surgery: bypass mode is unchanged.
    assert options.permission_mode == "bypassPermissions"


def test_build_chat_options_web_tools_disabled_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.agents.chat_agent.settings.firecrawl_api_key", "")
    options = build_chat_options(asyncio.Queue(), 1, None, "{}")

    assert "Bash" not in options.allowed_tools
    assert "FIRECRAWL_API_KEY" not in options.env


def test_key_material_masked_in_events() -> None:
    """fc- keys are scrubbed from tool inputs and result previews."""
    from src.agents.chat_agent import (
        _mask_key_material,
        _masked_payload,
        _result_preview,
    )

    assert (
        _mask_key_material("ran with fc-0000fake0000fake0000 oops")
        == "ran with fc-<redacted> oops"
    )
    assert (
        _masked_payload({"command": "firecrawl search --api-key fc-1111fake1111"})[
            "command"
        ]
        == "firecrawl search --api-key fc-<redacted>"
    )
    assert "fc-<redacted>" in _result_preview("error: bad key fc-1111fake1111")


def test_anthropic_key_masked_in_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """sk-ant- keys (now in the subprocess env, so `env` in Bash can print
    them) are scrubbed by pattern and by exact configured value."""
    from src.agents.chat_agent import _mask_key_material, _result_preview

    monkeypatch.setattr(
        "src.agents.chat_agent.settings.anthropic_api_key", "custom-key-no-prefix"
    )
    assert (
        _mask_key_material("ANTHROPIC_API_KEY=sk-ant-usr-AAAA_fake-BBBB\nX=1")
        == "ANTHROPIC_API_KEY=sk-ant-<redacted>\nX=1"
    )
    assert "custom-key-no-prefix" not in _result_preview(
        "env: KEY=custom-key-no-prefix"
    )


def test_result_preview_masks_key_straddling_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured key crossing the preview cut is masked before truncation,
    so no prefix of it survives in the preview."""
    from src.agents.chat_agent import RESULT_PREVIEW_LIMIT, _result_preview

    key = "custom-key-no-prefix-0000"
    monkeypatch.setattr("src.agents.chat_agent.settings.anthropic_api_key", key)
    text = "x" * (RESULT_PREVIEW_LIMIT - 10) + key + " tail"

    preview = _result_preview(text)

    assert key[:10] not in preview
    assert preview.endswith("…")


def test_short_configured_keys_do_not_mangle_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Placeholder keys like "test" are too short for exact-value masking —
    replacing them would rewrite ordinary words in the transcript."""
    from src.agents.chat_agent import _mask_key_material

    monkeypatch.setattr("src.agents.chat_agent.settings.anthropic_api_key", "test")
    monkeypatch.setattr("src.agents.chat_agent.settings.firecrawl_api_key", "local")
    assert (
        _mask_key_material("run the test suite against a local server")
        == "run the test suite against a local server"
    )


@patch("src.agents.chat_agent.ClaudeSDKClient", FakeClient)
async def test_anthropic_key_never_reaches_events_or_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through drive_chat_turn: a key surfacing in any projection
    (thinking, text, tool input, tool result) is redacted in every SSE event,
    the persisted trace, and the returned text."""
    key = "sk-ant-usr-FAKE_unit-test-key-0000"
    monkeypatch.setattr("src.agents.chat_agent.settings.anthropic_api_key", key)
    FakeClient.messages = [
        AssistantMessage(
            content=[
                ThinkingBlock(thinking=f"env printed {key}", signature="sig"),
                TextBlock(text=f"Your key is {key}"),
                ToolUseBlock(id="t1", name="Bash", input={"command": f"echo {key}"}),
            ],
            model="test-model",
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="t1",
                    content=[{"type": "text", "text": f"ANTHROPIC_API_KEY={key}"}],
                    is_error=False,
                )
            ]
        ),
        _result(),
    ]
    queue: asyncio.Queue = asyncio.Queue()
    options = build_chat_options(queue, 1, None, "{}")

    _, text, trace = await drive_chat_turn("hello", options, queue)

    events = [queue.get_nowait() for _ in range(queue.qsize())]
    assert [kind for kind, _ in events] == [
        "thinking",
        "text",
        "tool_use",
        "tool_result",
    ]
    for surface in (events, trace, text):
        dumped = json.dumps(surface)
        assert key not in dumped
        assert "sk-ant-<redacted>" in dumped


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


async def test_publish_tool_persists_and_queues(
    monkeypatch, session_factory, db_patient
):
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


async def test_publish_tool_masks_key_material(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    db_patient: Patient,
) -> None:
    """A key the model copies into a briefing field (e.g. from Bash output) is
    redacted in both the persisted row and the briefing_published event, while
    ordinary clinical text passes through untouched."""
    key = "sk-ant-usr-FAKE_unit-test-key-0000"
    monkeypatch.setattr("src.database.async_session", session_factory)
    monkeypatch.setattr("src.agents.chat_agent.settings.anthropic_api_key", key)
    args = {
        **VALID_STRUCTURED_OUTPUT,
        "summary": {
            **VALID_STRUCTURED_OUTPUT["summary"],
            "one_liner": f"Env showed {key}",
        },
    }
    queue: asyncio.Queue = asyncio.Queue()
    publish = make_publish_tool(queue, db_patient.id)

    await publish.handler(args)

    _, payload = queue.get_nowait()
    async with session_factory() as session:
        stored = (await session.scalars(select(Briefing))).one()
    for surface in (payload, stored.content):
        assert key not in json.dumps(surface)
        assert surface["summary"]["one_liner"] == "Env showed sk-ant-<redacted>"
        assert surface["flags"] == VALID_STRUCTURED_OUTPUT["flags"]


async def test_publish_tool_rejects_invalid_payload(monkeypatch, session_factory):
    monkeypatch.setattr("src.database.async_session", session_factory)
    queue: asyncio.Queue = asyncio.Queue()
    publish = make_publish_tool(queue, 1)

    response = await publish.handler({"flags": "not-a-list"})

    assert response["isError"] is True
    assert queue.empty()
    async with session_factory() as session:
        assert (await session.scalars(select(Briefing))).all() == []
