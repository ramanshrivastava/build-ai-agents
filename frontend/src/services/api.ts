import type {
  ApiErrorDetail,
  BriefingRuntime,
  ChatEvent,
  ChatHistoryResponse,
  Patient,
  PatientBriefing,
} from "@/types";

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

/**
 * Incremental SSE frame parser.
 *
 * SSE frames arrive as `event: <name>\ndata: <json>\n\n`, but network chunks
 * can split anywhere — even mid-line — so the caller keeps the unparsed tail
 * (`rest`) and passes it back in with the next chunk. Pure function so it can
 * be unit-tested without a network.
 */
export function parseSSEChunk(
  buffer: string,
  chunk: string,
): { events: ChatEvent[]; rest: string } {
  const combined = buffer + chunk;
  const frames = combined.split("\n\n");
  // The last segment is either "" (clean frame boundary) or a partial frame.
  const rest = frames.pop() ?? "";
  const events: ChatEvent[] = [];

  for (const frame of frames) {
    let eventName = "";
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event: ")) eventName = line.slice(7).trim();
      else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
    }
    if (!eventName) continue;
    const data = dataLines.length > 0 ? JSON.parse(dataLines.join("\n")) : {};

    switch (eventName) {
      case "text":
        events.push({ kind: "text", text: data.text });
        break;
      case "tool_use":
        events.push({ kind: "tool_use", tool: data.tool, input: data.input });
        break;
      case "tool_result":
        events.push({ kind: "tool_result" });
        break;
      case "briefing_published":
        // The data payload IS the briefing (BriefingResponse shape).
        events.push({ kind: "briefing_published", briefing: data });
        break;
      case "done":
        events.push({ kind: "done", session_id: data.session_id ?? null });
        break;
      case "error":
        events.push({ kind: "error", code: data.code, message: data.message });
        break;
    }
  }
  return { events, rest };
}

export const api = {
  getPatients: () => fetchJson<Patient[]>("/api/v1/patients"),

  getPatient: (id: number) => fetchJson<Patient>(`/api/v1/patients/${id}`),

  generateBriefing: (patientId: number, runtime: BriefingRuntime = "sdk") => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120_000);
    const endpoint =
      runtime === "managed"
        ? `/api/v1/patients/${patientId}/briefing/managed`
        : `/api/v1/patients/${patientId}/briefing`;

    return fetchJson<PatientBriefing>(endpoint, {
      method: "POST",
      signal: controller.signal,
    }).finally(() => clearTimeout(timeout));
  },

  getChat: (patientId: number) =>
    fetchJson<ChatHistoryResponse>(`/api/v1/patients/${patientId}/chat`),

  // Raw fetch: the 204 response has no body, so fetchJson's .json() would throw.
  resetChat: async (patientId: number): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/patients/${patientId}/chat`, {
      method: "DELETE",
    });
    if (!response.ok) {
      throw new ApiError(response.status, {
        code: "UNKNOWN",
        message: response.statusText,
      });
    }
  },

  /**
   * Run one chat turn, invoking onEvent for each SSE event as it arrives.
   *
   * Uses fetch + ReadableStream rather than EventSource because EventSource
   * only supports GET and we need to POST the message body.
   */
  streamChat: async (
    patientId: number,
    message: string,
    onEvent: (event: ChatEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/v1/patients/${patientId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      signal,
    });

    if (!response.ok || !response.body) {
      let detail: ApiErrorDetail;
      try {
        detail = (await response.json()).detail;
      } catch {
        detail = { code: "UNKNOWN", message: response.statusText };
      }
      throw new ApiError(response.status, detail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      const parsed = parseSSEChunk(buffer, decoder.decode(value, { stream: true }));
      buffer = parsed.rest;
      parsed.events.forEach(onEvent);
    }
  },
};
