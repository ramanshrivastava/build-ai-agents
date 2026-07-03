"""SQLAlchemy ORM models."""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    date_of_birth: Mapped[datetime.date]
    gender: Mapped[str] = mapped_column(String(10))
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    medications: Mapped[list] = mapped_column(JSON, default=list)
    labs: Mapped[list] = mapped_column(JSON, default=list)
    allergies: Mapped[list] = mapped_column(JSON, default=list)
    visits: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class ManagedAgentSession(Base):
    """Maps a patient to a reusable Claude Managed Agents session."""

    __tablename__ = "managed_agent_sessions"
    __table_args__ = (
        UniqueConstraint("patient_id", name="uq_managed_session_patient"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE")
    )
    session_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    last_used_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class Briefing(Base):
    """A generated patient briefing — the anchor for follow-up conversation.

    Stored as the serialized BriefingResponse so follow-up questions can reuse
    the exact briefing the physician saw without regenerating it.
    """

    __tablename__ = "briefings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class BriefingMessage(Base):
    """One turn of the follow-up conversation about a briefing."""

    __tablename__ = "briefing_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    briefing_id: Mapped[int] = mapped_column(
        ForeignKey("briefings.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class Conversation(Base):
    """The unified chat thread for a patient (one active conversation each).

    `session_id` is the Claude Agent SDK session identifier: the SDK keeps the
    full transcript client-side (~/.claude/projects/), and each new turn resumes
    it via ClaudeAgentOptions(resume=session_id) — the web equivalent of
    `claude --resume`. It is NULL until the first turn completes.
    """

    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("patient_id", name="uq_conversation_patient"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE")
    )
    session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())


class ConversationMessage(Base):
    """One rendered chat turn, stored for UI history only.

    The authoritative conversation state lives in the SDK's session transcript
    (see Conversation.session_id); these rows just let the frontend re-render
    the thread after a page refresh without touching the agent.
    """

    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
