"""API tests for the unified chat endpoints — mocks at the service layer."""

from __future__ import annotations

from sqlalchemy import select

from src.models.orm import Briefing, Conversation, ConversationMessage
from tests.test_briefing_agent import VALID_STRUCTURED_OUTPUT


async def _fake_stream(session, patient, message):
    yield b'event: text\ndata: {"text": "hi"}\n\n'
    yield b'event: done\ndata: {"session_id": "s-1"}\n\n'


async def test_chat_streams_sse(client, seed_patient, mocker):
    mocker.patch("src.routers.chat.stream_chat_turn", _fake_stream)

    async with client.stream(
        "POST",
        f"/api/v1/patients/{seed_patient.id}/chat",
        json={"message": "hello"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = (await response.aread()).decode()

    # Two well-formed SSE frames, in order.
    frames = [f for f in body.split("\n\n") if f]
    assert frames[0] == 'event: text\ndata: {"text": "hi"}'
    assert frames[1] == 'event: done\ndata: {"session_id": "s-1"}'


async def test_chat_unknown_patient_404(client):
    response = await client.post("/api/v1/patients/999/chat", json={"message": "hi"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PATIENT_NOT_FOUND"


async def test_history_round_trip(client, seed_patient, session_factory):
    async with session_factory() as session:
        conversation = Conversation(patient_id=seed_patient.id, session_id="s-1")
        session.add(conversation)
        await session.flush()
        session.add_all(
            [
                ConversationMessage(
                    conversation_id=conversation.id, role="user", content="who?"
                ),
                ConversationMessage(
                    conversation_id=conversation.id, role="assistant", content="Maria."
                ),
            ]
        )
        session.add(
            Briefing(patient_id=seed_patient.id, content=VALID_STRUCTURED_OUTPUT)
        )
        await session.commit()
        conversation_id = conversation.id

    response = await client.get(f"/api/v1/patients/{seed_patient.id}/chat")

    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == conversation_id
    assert [m["role"] for m in data["messages"]] == ["user", "assistant"]
    assert data["latest_briefing"]["id"] is not None
    assert len(data["latest_briefing"]["flags"]) == len(
        VALID_STRUCTURED_OUTPUT["flags"]
    )


async def test_history_empty(client, seed_patient):
    response = await client.get(f"/api/v1/patients/{seed_patient.id}/chat")
    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": None,
        "messages": [],
        "latest_briefing": None,
    }


async def test_reset_deletes_conversation(client, seed_patient, session_factory):
    async with session_factory() as session:
        session.add(Conversation(patient_id=seed_patient.id, session_id="s-1"))
        await session.commit()

    response = await client.delete(f"/api/v1/patients/{seed_patient.id}/chat")
    assert response.status_code == 204

    async with session_factory() as session:
        remaining = (await session.scalars(select(Conversation))).all()
    assert remaining == []
