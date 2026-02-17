import type { ApiErrorDetail, Patient, PatientBriefing } from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: ApiErrorDetail;

  constructor(status: number, detail: ApiErrorDetail) {
    super(detail.message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let detail: ApiErrorDetail;
    try {
      detail = await response.json();
    } catch {
      detail = { code: "UNKNOWN", message: response.statusText };
    }
    throw new ApiError(response.status, detail);
  }

  return response.json();
}

export const api = {
  getPatients: () => fetchJson<Patient[]>("/api/v1/patients"),

  getPatient: (id: number) => fetchJson<Patient>(`/api/v1/patients/${id}`),

  generateBriefing: (patientId: number) => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120_000);

    return fetchJson<PatientBriefing>(`/api/v1/patients/${patientId}/briefing`, {
      method: "POST",
      signal: controller.signal,
    }).finally(() => clearTimeout(timeout));
  },
};
