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
    generated_at: datetime.datetime


# --- Error schema ---


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = {}
