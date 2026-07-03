/**
 * Shared TypeScript types for the Build AI Agents frontend.
 */

export interface LabResult {
  name: string;
  value: number;
  unit: string;
  date: string;
  reference_range: { min: number; max: number };
}

export interface Medication {
  name: string;
  dosage: string;
  frequency: string;
}

export interface Visit {
  date: string;
  reason: string;
}

export interface Patient {
  id: number;
  name: string;
  date_of_birth: string;
  gender: string;
  conditions: string[];
  medications: Medication[];
  labs: LabResult[];
  allergies: string[];
  visits: Visit[];
  created_at: string;
  updated_at: string;
}

export interface Flag {
  category: 'labs' | 'medications' | 'screenings' | 'ai_insight';
  severity: 'critical' | 'warning' | 'info';
  title: string;
  description: string;
  source: 'ai';
  suggested_action: string | null;
}

export interface BriefingSummary {
  one_liner: string;
  key_conditions: string[];
  relevant_history: string;
}

export interface SuggestedAction {
  action: string;
  reason: string;
  priority: number;
}

export interface PatientBriefing {
  flags: Flag[];
  summary: BriefingSummary;
  suggested_actions: SuggestedAction[];
  generated_at: string;
  /** Persisted briefing id (present when the backend stored it). */
  id?: number | null;
}

export type BriefingRuntime = 'sdk' | 'managed';

// --- Unified patient chat (SSE) ---

export type ChatRole = 'user' | 'assistant';

/** One rendered bubble in the chat thread. */
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  status?: 'streaming' | 'done' | 'error';
  /** Live tool activity shown under the bubble (e.g. "Searching guidelines…"). */
  activity?: string | null;
}

/**
 * Discriminated union mirroring the backend's SSE event vocabulary
 * (see backend/src/routers/chat.py): one variant per `event:` name.
 */
export type ChatEvent =
  | { kind: 'text'; text: string }
  | { kind: 'tool_use'; tool: string; input: Record<string, unknown> }
  | { kind: 'tool_result' }
  | { kind: 'briefing_published'; briefing: PatientBriefing }
  | { kind: 'done'; session_id: string | null }
  | { kind: 'error'; code: string; message: string };

export interface ChatHistoryMessage {
  role: ChatRole;
  content: string;
  created_at: string;
}

export interface ChatHistoryResponse {
  conversation_id: number | null;
  messages: ChatHistoryMessage[];
  latest_briefing: PatientBriefing | null;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}
