"""Patient endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient


async def test_list_patients_empty(client: AsyncClient) -> None:
    response = await client.get("/api/v1/patients")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_patients(client: AsyncClient, seed_patient) -> None:
    response = await client.get("/api/v1/patients")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Patient"


async def test_get_patient(client: AsyncClient, seed_patient) -> None:
    response = await client.get(f"/api/v1/patients/{seed_patient.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Patient"
    assert data["gender"] == "F"
    assert data["conditions"] == ["Type 2 Diabetes"]


async def test_get_patient_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/v1/patients/999")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "PATIENT_NOT_FOUND"
