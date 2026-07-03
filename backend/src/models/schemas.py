"""Pydantic request/response/error schemas."""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


# --- Patient API schemas ---


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    date_of_birth: datetime.date
    gender: str
    conditions: list[str]
    medications: list[dict]
    labs: list[dict]
    allergies: list[str]
    visits: list[dict]
    created_at: datetime.datetime
    updated_at: datetime.datetime


# --- Briefing schemas (agent output — no generated_at) ---


class Flag(BaseModel):
    category: Literal["labs", "medications", "screenings", "ai_insight"]
    severity: Literal["critical", "warning", "info"]
    title: str
    description: str
    source: Literal["ai"]
    suggested_action: str | None = None


class Summary(BaseModel):
    one_liner: str
    key_conditions: list[str]
    relevant_history: str


class SuggestedAction(BaseModel):
    action: str
    reason: str
    priority: int


class PatientBriefing(BaseModel):
    flags: list[Flag]
    summary: Summary
    suggested_actions: list[SuggestedAction]


# --- API response wrapper (adds server-side timestamp) ---


class BriefingResponse(PatientBriefing):
    # Persisted briefing id, used to open a follow-up conversation. None when the
    # briefing was not stored (e.g. endpoints that don't persist).
    id: int | None = None
    generated_at: datetime.datetime


# --- Follow-up chat (conversational) ---


class BriefingChatRequest(BaseModel):
    question: str


class BriefingChatMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    created_at: datetime.datetime


class BriefingChatResponse(BaseModel):
    briefing_id: int
    answer: str
    history: list[BriefingChatMessage]


# --- Unified patient chat (SSE) ---


class ChatRequest(BaseModel):
    message: str


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    created_at: datetime.datetime


class ChatHistoryResponse(BaseModel):
    """Everything the UI needs to rehydrate a patient's chat after a refresh."""

    conversation_id: int | None
    messages: list[ChatMessageOut]
    latest_briefing: BriefingResponse | None


# --- Error schema ---


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = {}
