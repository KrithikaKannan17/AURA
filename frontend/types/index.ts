export type Severity = "P1" | "P2" | "P3";

export type RunbookStatus = "processing" | "indexed" | "failed";
export type IncidentStatus =
  | "open"
  | "diagnosing"
  | "workflow_ready"
  | "executing"
  | "resolved"
  | "escalated"
  | "failed";
export type StepStatus =
  | "pending"
  | "running"
  | "done"
  | "failed"
  | "skipped"
  | "awaiting_confirmation";
export type EscalationDeliveryStatus = "pending" | "sent" | "failed";

export interface Runbook {
  id: number;
  filename: string;
  original_filename: string;
  file_type: string;
  chunk_count: number;
  status: RunbookStatus;
  created_at: string;
}

export interface Source {
  source_file: string;
  section_title: string;
  page_number: number;
  relevance_score: number;
  excerpt: string;
}

export interface Incident {
  id: number;
  title: string;
  description: string;
  severity: Severity;
  system_affected: string;
  status: IncidentStatus;
  root_cause: string | null;
  confidence_score: number | null;
  remediation_steps: string[] | null;
  sources: Source[] | null;
  current_step: number;
  created_at: string;
  updated_at: string | null;
}

export interface WorkflowStep {
  id: number;
  incident_id: number;
  step_id: number;
  action: string;
  command: string | null;
  expected_outcome: string | null;
  rollback: string | null;
  is_destructive: boolean;
  requires_confirmation: boolean;
  status: StepStatus;
  output: string | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface EscalationReport {
  incident_summary: string;
  attempted_steps: string[];
  failure_reason: string;
  recommended_on_call_action: string;
  risk_assessment: string;
  estimated_impact: string;
}

export interface Escalation {
  id: number;
  incident_id: number;
  reason: string;
  summary: string | null;
  failure_reason: string | null;
  recommended_action: string | null;
  slack_status: EscalationDeliveryStatus;
  pagerduty_status: EscalationDeliveryStatus;
  created_at: string;
}

export interface IncidentDetail {
  incident: Incident;
  workflow_steps: WorkflowStep[];
  escalation: Escalation | null;
}

export interface DiagnoseRequest {
  incident_description: string;
  severity: Severity;
  system_affected: string;
  title?: string;
}

export interface WsMessage {
  type:
    | "initial_state"
    | "step_update"
    | "execution_complete"
    | "error"
    | "pong";
  steps?: WorkflowStep[];
  step_id?: number;
  status?: StepStatus | "resolved";
  message?: string;
  output?: string;
  incident_id?: number;
}
