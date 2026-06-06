"""SQLAlchemy ORM models."""

from __future__ import annotations

import datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, func
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
