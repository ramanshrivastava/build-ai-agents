"""Unit tests for Claude Managed Agents briefing service."""

from __future__ import annotations

import datetime
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.models.orm import ManagedAgentSession, Patient
from src.services.briefing_service import BriefingGenerationError
from src.services import managed_briefing_service as svc


@pytest.fixture
def fake_patient() -> Patient:
    return Patient(
        id=1,
        name="Maria Garcia",
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


VALID_JSON = {
    "flags": [
        {
            "category": "labs",
            "severity": "warning",
            "title": "HbA1c elevated",
            "description": "HbA1c is above target [1]",
            "source": "ai",
            "suggested_action": "Review diabetes plan",
        }
    ],
    "summary": {
        "one_liner": "67-year-old female with Type 2 Diabetes",
        "key_conditions": ["Type 2 Diabetes"],
        "relevant_history": "Synthetic patient record reviewed.",
    },
    "suggested_actions": [
        {
            "action": "Review HbA1c",
            "reason": "Current value is above target [1]",
            "priority": 1,
        }
    ],
}


class _AsyncEvents:
    def __init__(self, *batches: list[SimpleNamespace]) -> None:
        self.batches = list(batches)
        self.send = AsyncMock(return_value=SimpleNamespace())

    def list(self, *_args: Any, **_kwargs: Any) -> AsyncIterator[SimpleNamespace]:
        batch = self.batches.pop(0) if self.batches else []

        async def _iter() -> AsyncIterator[SimpleNamespace]:
            for event in batch:
                yield event

        return _iter()


def _client_with_events(events: _AsyncEvents) -> SimpleNamespace:
    return SimpleNamespace(
        beta=SimpleNamespace(
            sessions=SimpleNamespace(
                create=AsyncMock(return_value=SimpleNamespace(id="sess_123")),
                delete=AsyncMock(return_value=SimpleNamespace(id="sess_123")),
                events=events,
            )
        )
    )


@pytest.fixture(autouse=True)
def managed_settings(monkeypatch):
    monkeypatch.setattr(svc.settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(svc.settings, "managed_agent_id", "agent_123")
    monkeypatch.setattr(svc.settings, "managed_environment_id", "env_123")
    monkeypatch.setattr(svc.settings, "managed_agent_session_timeout_seconds", 2)
    monkeypatch.setattr(svc.settings, "managed_agent_max_tool_rounds", 4)


async def test_generate_managed_briefing_requires_config(monkeypatch, fake_patient):
    monkeypatch.setattr(svc.settings, "managed_agent_id", "")

    with pytest.raises(BriefingGenerationError) as exc_info:
        await svc.generate_managed_briefing(AsyncMock(), fake_patient)

    assert exc_info.value.code == "MANAGED_AGENTS_NOT_CONFIGURED"


async def test_get_or_create_session_creates_and_reuses(session_factory, fake_patient):
    events = _AsyncEvents([])
    client = _client_with_events(events)

    async with session_factory() as db:
        db.add(fake_patient)
        await db.commit()

        first = await svc._get_or_create_session(db, client, fake_patient)
        second = await svc._get_or_create_session(db, client, fake_patient)

    assert first.session_id == "sess_123"
    assert second.session_id == "sess_123"
    client.beta.sessions.create.assert_awaited_once()


async def test_wait_handles_custom_tool_and_returns_json(monkeypatch):
    tool_event = SimpleNamespace(
        id="tool_1",
        type="agent.custom_tool_use",
        name="search_clinical_guidelines",
        input={"query": "diabetes", "max_results": 1},
    )
    message_event = SimpleNamespace(
        id="msg_1",
        type="agent.message",
        content=[
            SimpleNamespace(
                text='{"flags":[],"summary":{"one_liner":"ok","key_conditions":[],"relevant_history":""},"suggested_actions":[]}'
            )
        ],
    )
    idle_event = SimpleNamespace(
        id="idle_1",
        type="session.status_idle",
        stop_reason=SimpleNamespace(type="end_turn"),
    )
    events = _AsyncEvents([tool_event], [message_event, idle_event])
    client = _client_with_events(events)
    handler = AsyncMock(
        return_value={"content": [{"type": "text", "text": "<sources/>"}]}
    )
    monkeypatch.setattr(
        svc.search_clinical_guidelines,
        "handler",
        handler,
    )

    result = await svc._wait_for_briefing_json(client, "sess_123", set())

    assert result["summary"]["one_liner"] == "ok"
    handler.assert_awaited_once_with({"query": "diabetes", "max_results": 1})
    assert client.beta.sessions.events.send.await_count == 1
    sent = client.beta.sessions.events.send.await_args.kwargs["events"][0]
    assert sent["type"] == "user.custom_tool_result"
    assert sent["custom_tool_use_id"] == "tool_1"


async def test_list_event_ids_answers_orphaned_tool_calls():
    orphan = SimpleNamespace(
        id="tool_orphan",
        type="agent.custom_tool_use",
        name="search_clinical_guidelines",
        input={"query": "diabetes"},
    )
    answered_use = SimpleNamespace(
        id="tool_done",
        type="agent.custom_tool_use",
        name="search_clinical_guidelines",
        input={"query": "hba1c"},
    )
    answered_result = SimpleNamespace(
        id="res_1",
        type="user.custom_tool_result",
        custom_tool_use_id="tool_done",
    )
    events = _AsyncEvents([orphan, answered_use, answered_result])
    client = _client_with_events(events)

    seen = await svc._list_event_ids(client, "sess_123")

    assert seen == {"tool_orphan", "tool_done", "res_1"}
    assert client.beta.sessions.events.send.await_count == 1
    sent = client.beta.sessions.events.send.await_args.kwargs["events"][0]
    assert sent["type"] == "user.custom_tool_result"
    assert sent["custom_tool_use_id"] == "tool_orphan"
    assert sent["is_error"] is True


async def test_generate_validates_final_schema(
    monkeypatch, session_factory, fake_patient
):
    monkeypatch.setattr(svc, "_list_event_ids", AsyncMock(return_value=set()))
    monkeypatch.setattr(svc, "_send_patient_message", AsyncMock())
    monkeypatch.setattr(
        svc, "_wait_for_briefing_json", AsyncMock(return_value=VALID_JSON)
    )
    client = _client_with_events(_AsyncEvents([]))
    monkeypatch.setattr(svc, "_client", lambda: client)

    async with session_factory() as db:
        db.add(fake_patient)
        await db.commit()
        result = await svc.generate_managed_briefing(db, fake_patient)

    assert result.summary.one_liner == "67-year-old female with Type 2 Diabetes"
    assert result.generated_at is not None


async def test_reset_managed_session_removes_mapping(
    monkeypatch, session_factory, fake_patient
):
    client = _client_with_events(_AsyncEvents([]))
    monkeypatch.setattr(svc, "_client", lambda: client)

    async with session_factory() as db:
        db.add(fake_patient)
        db.add(ManagedAgentSession(patient_id=1, session_id="sess_123"))
        await db.commit()

        await svc.reset_managed_session(db, 1)

        result = await db.execute(select(ManagedAgentSession))

    assert result.scalar_one_or_none() is None
    client.beta.sessions.delete.assert_awaited_once_with("sess_123")
