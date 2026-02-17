"""Seed database with 5 realistic patients. Drop-and-recreate tables on each run."""

from __future__ import annotations

import asyncio
import datetime

from src.database import async_session, engine
from src.models.orm import Base, Patient


PATIENTS = [
    Patient(
        name="Maria Garcia",
        date_of_birth=datetime.date(1957, 3, 15),
        gender="F",
        conditions=["Type 2 Diabetes", "Hypertension", "CKD Stage 3"],
        medications=[
            {"name": "Metformin", "dosage": "1000mg", "frequency": "twice daily"},
            {"name": "Lisinopril", "dosage": "20mg", "frequency": "once daily"},
            {"name": "Amlodipine", "dosage": "5mg", "frequency": "once daily"},
            {"name": "Atorvastatin", "dosage": "40mg", "frequency": "once daily"},
        ],
        labs=[
            {
                "name": "HbA1c",
                "value": 7.2,
                "unit": "%",
                "date": "2024-01-15",
                "reference_range": {"min": 4.0, "max": 5.6},
            },
            {
                "name": "eGFR",
                "value": 45,
                "unit": "mL/min/1.73m2",
                "date": "2024-01-15",
                "reference_range": {"min": 60, "max": 120},
            },
            {
                "name": "Creatinine",
                "value": 1.8,
                "unit": "mg/dL",
                "date": "2024-01-15",
                "reference_range": {"min": 0.6, "max": 1.2},
            },
            {
                "name": "Blood Pressure",
                "value": 145,
                "unit": "mmHg systolic",
                "date": "2024-01-15",
                "reference_range": {"min": 90, "max": 130},
            },
            {
                "name": "LDL Cholesterol",
                "value": 110,
                "unit": "mg/dL",
                "date": "2024-01-15",
                "reference_range": {"min": 0, "max": 100},
            },
            {
                "name": "Potassium",
                "value": 4.8,
                "unit": "mEq/L",
                "date": "2024-01-15",
                "reference_range": {"min": 3.5, "max": 5.0},
            },
        ],
        allergies=["Penicillin", "Sulfa drugs"],
        visits=[
            {"date": "2024-01-15", "reason": "Diabetes follow-up"},
            {"date": "2023-10-20", "reason": "CKD monitoring"},
            {"date": "2023-07-12", "reason": "Hypertension check"},
            {"date": "2023-04-05", "reason": "Annual physical"},
        ],
    ),
    Patient(
        name="James Wilson",
        date_of_birth=datetime.date(1980, 8, 22),
        gender="M",
        conditions=["Hypertension", "Generalized Anxiety Disorder"],
        medications=[
            {"name": "Lisinopril", "dosage": "10mg", "frequency": "once daily"},
            {"name": "Sertraline", "dosage": "50mg", "frequency": "once daily"},
        ],
        labs=[
            {
                "name": "Blood Pressure",
                "value": 138,
                "unit": "mmHg systolic",
                "date": "2024-02-10",
                "reference_range": {"min": 90, "max": 130},
            },
            {
                "name": "Total Cholesterol",
                "value": 215,
                "unit": "mg/dL",
                "date": "2024-02-10",
                "reference_range": {"min": 0, "max": 200},
            },
            {
                "name": "Fasting Glucose",
                "value": 95,
                "unit": "mg/dL",
                "date": "2024-02-10",
                "reference_range": {"min": 70, "max": 100},
            },
            {
                "name": "TSH",
                "value": 2.1,
                "unit": "mIU/L",
                "date": "2024-02-10",
                "reference_range": {"min": 0.4, "max": 4.0},
            },
        ],
        allergies=[],
        visits=[
            {"date": "2024-02-10", "reason": "Blood pressure follow-up"},
            {"date": "2023-11-15", "reason": "Anxiety medication review"},
            {"date": "2023-08-20", "reason": "Annual physical"},
        ],
    ),
    Patient(
        name="Sarah Chen",
        date_of_birth=datetime.date(1993, 11, 8),
        gender="F",
        conditions=[],
        medications=[],
        labs=[
            {
                "name": "CBC - WBC",
                "value": 6.5,
                "unit": "K/uL",
                "date": "2024-03-01",
                "reference_range": {"min": 4.0, "max": 11.0},
            },
            {
                "name": "Hemoglobin",
                "value": 13.2,
                "unit": "g/dL",
                "date": "2024-03-01",
                "reference_range": {"min": 12.0, "max": 16.0},
            },
            {
                "name": "Fasting Glucose",
                "value": 82,
                "unit": "mg/dL",
                "date": "2024-03-01",
                "reference_range": {"min": 70, "max": 100},
            },
        ],
        allergies=[],
        visits=[
            {"date": "2024-03-01", "reason": "Annual checkup"},
            {"date": "2023-03-15", "reason": "Annual checkup"},
            {"date": "2022-04-10", "reason": "Annual checkup"},
        ],
    ),
    Patient(
        name="Robert Johnson",
        date_of_birth=datetime.date(1953, 5, 30),
        gender="M",
        conditions=[
            "Congestive Heart Failure",
            "Atrial Fibrillation",
            "COPD",
        ],
        medications=[
            {"name": "Furosemide", "dosage": "40mg", "frequency": "once daily"},
            {"name": "Metoprolol", "dosage": "50mg", "frequency": "twice daily"},
            {"name": "Warfarin", "dosage": "5mg", "frequency": "once daily"},
            {"name": "Tiotropium", "dosage": "18mcg", "frequency": "once daily"},
            {"name": "Lisinopril", "dosage": "10mg", "frequency": "once daily"},
        ],
        labs=[
            {
                "name": "BNP",
                "value": 450,
                "unit": "pg/mL",
                "date": "2024-01-20",
                "reference_range": {"min": 0, "max": 100},
            },
            {
                "name": "INR",
                "value": 2.3,
                "unit": "",
                "date": "2024-01-20",
                "reference_range": {"min": 2.0, "max": 3.0},
            },
            {
                "name": "Creatinine",
                "value": 1.4,
                "unit": "mg/dL",
                "date": "2024-01-20",
                "reference_range": {"min": 0.7, "max": 1.3},
            },
            {
                "name": "Potassium",
                "value": 5.2,
                "unit": "mEq/L",
                "date": "2024-01-20",
                "reference_range": {"min": 3.5, "max": 5.0},
            },
            {
                "name": "Hemoglobin",
                "value": 11.8,
                "unit": "g/dL",
                "date": "2024-01-20",
                "reference_range": {"min": 13.5, "max": 17.5},
            },
            {
                "name": "SpO2",
                "value": 92,
                "unit": "%",
                "date": "2024-01-20",
                "reference_range": {"min": 95, "max": 100},
            },
            {
                "name": "Sodium",
                "value": 134,
                "unit": "mEq/L",
                "date": "2024-01-20",
                "reference_range": {"min": 136, "max": 145},
            },
            {
                "name": "eGFR",
                "value": 52,
                "unit": "mL/min/1.73m2",
                "date": "2024-01-20",
                "reference_range": {"min": 60, "max": 120},
            },
        ],
        allergies=["Aspirin", "Codeine"],
        visits=[
            {"date": "2024-01-20", "reason": "CHF exacerbation follow-up"},
            {"date": "2023-12-05", "reason": "INR check"},
            {"date": "2023-10-18", "reason": "COPD exacerbation"},
            {"date": "2023-08-22", "reason": "Cardiology follow-up"},
            {"date": "2023-06-10", "reason": "Pulmonology follow-up"},
        ],
    ),
    Patient(
        name="Emily Thompson",
        date_of_birth=datetime.date(1970, 12, 3),
        gender="F",
        conditions=["Hypothyroidism", "Osteoporosis"],
        medications=[
            {"name": "Levothyroxine", "dosage": "75mcg", "frequency": "once daily"},
            {"name": "Alendronate", "dosage": "70mg", "frequency": "once weekly"},
            {
                "name": "Calcium + Vitamin D",
                "dosage": "600mg/400IU",
                "frequency": "twice daily",
            },
        ],
        labs=[
            {
                "name": "TSH",
                "value": 5.8,
                "unit": "mIU/L",
                "date": "2024-02-20",
                "reference_range": {"min": 0.4, "max": 4.0},
            },
            {
                "name": "Free T4",
                "value": 0.9,
                "unit": "ng/dL",
                "date": "2024-02-20",
                "reference_range": {"min": 0.8, "max": 1.8},
            },
            {
                "name": "Vitamin D",
                "value": 28,
                "unit": "ng/mL",
                "date": "2024-02-20",
                "reference_range": {"min": 30, "max": 100},
            },
            {
                "name": "Calcium",
                "value": 9.2,
                "unit": "mg/dL",
                "date": "2024-02-20",
                "reference_range": {"min": 8.5, "max": 10.5},
            },
            {
                "name": "DEXA T-score (spine)",
                "value": -2.8,
                "unit": "SD",
                "date": "2023-09-15",
                "reference_range": {"min": -1.0, "max": 999},
            },
        ],
        allergies=["Latex"],
        visits=[
            {"date": "2024-02-20", "reason": "Thyroid follow-up"},
            {"date": "2023-09-15", "reason": "DEXA scan results"},
            {"date": "2023-06-01", "reason": "Annual physical"},
        ],
    ),
]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        session.add_all(PATIENTS)
        await session.commit()

    print(f"Seeded {len(PATIENTS)} patients.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
