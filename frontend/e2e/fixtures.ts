import type { Page } from "@playwright/test";

export const patients = [
  {
    id: 1,
    name: "Maria Garcia",
    date_of_birth: "1957-03-15",
    gender: "Female",
    conditions: ["Type 2 Diabetes", "Hypertension", "CKD Stage 3"],
    medications: [
      { name: "Metformin", dosage: "1000mg", frequency: "twice daily" },
      { name: "Lisinopril", dosage: "20mg", frequency: "once daily" },
    ],
    labs: [
      {
        name: "HbA1c",
        value: 7.2,
        unit: "%",
        date: "2024-01-15",
        reference_range: { min: 4, max: 5.6 },
      },
      {
        name: "eGFR",
        value: 45,
        unit: "mL/min/1.73m2",
        date: "2024-01-15",
        reference_range: { min: 60, max: 120 },
      },
    ],
    allergies: ["Penicillin"],
    visits: [{ date: "2024-01-15", reason: "Diabetes follow-up" }],
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-15T00:00:00Z",
  },
  {
    id: 2,
    name: "James Wilson",
    date_of_birth: "1980-07-22",
    gender: "Male",
    conditions: ["Hypertension"],
    medications: [
      { name: "Lisinopril", dosage: "10mg", frequency: "once daily" },
    ],
    labs: [
      {
        name: "Blood Pressure",
        value: 138,
        unit: "mmHg systolic",
        date: "2024-02-10",
        reference_range: { min: 90, max: 130 },
      },
    ],
    allergies: [],
    visits: [{ date: "2024-02-10", reason: "Blood pressure follow-up" }],
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-02-10T00:00:00Z",
  },
];

export const briefing = {
  flags: [
    {
      category: "labs" as const,
      severity: "critical" as const,
      title: "Elevated HbA1c",
      description: "HbA1c of 7.2% is above the target range of 4-5.6%",
      source: "ai" as const,
      suggested_action: "Consider adjusting diabetes medication",
    },
    {
      category: "medications" as const,
      severity: "warning" as const,
      title: "Drug interaction risk",
      description: "Potential interaction between current medications",
      source: "ai" as const,
      suggested_action: "Review medication list with pharmacist",
    },
  ],
  summary: {
    one_liner:
      "68-year-old female with poorly controlled diabetes and declining kidney function",
    key_conditions: ["Type 2 Diabetes", "CKD Stage 3"],
    relevant_history: "Progressive CKD with eGFR declining over past year",
  },
  suggested_actions: [
    { action: "Review HbA1c management", reason: "Above target", priority: 1 },
    { action: "Monitor kidney function", reason: "CKD Stage 3", priority: 2 },
  ],
  generated_at: new Date().toISOString(),
};

export async function mockApi(page: Page) {
  await page.route("**/api/v1/patients", (route) => {
    route.fulfill({ json: patients });
  });

  await page.route("**/api/v1/patients/1", (route) => {
    route.fulfill({ json: patients[0] });
  });

  await page.route("**/api/v1/patients/2", (route) => {
    route.fulfill({ json: patients[1] });
  });

  await page.route("**/api/v1/patients/1/briefing", (route) => {
    route.fulfill({ json: briefing });
  });

  await page.route("**/api/v1/patients/2/briefing", (route) => {
    route.fulfill({ json: briefing });
  });
}
