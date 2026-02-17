"""Test fixtures and configuration."""

from __future__ import annotations

import datetime
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import get_session
from src.main import app
from src.models.orm import Base, Patient

test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
test_session_factory = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_session() -> AsyncIterator[AsyncSession]:
    async with test_session_factory() as session:
        yield session


app.dependency_overrides[get_session] = override_get_session


@pytest.fixture(autouse=True)
async def setup_database() -> AsyncIterator[None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def seed_patient() -> Patient:
    async with test_session_factory() as session:
        patient = Patient(
            name="Test Patient",
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
        session.add(patient)
        await session.commit()
        await session.refresh(patient)
        return patient
