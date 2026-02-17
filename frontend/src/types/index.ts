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
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}
