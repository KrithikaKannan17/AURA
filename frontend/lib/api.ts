import axios from "axios";
import type {
  DiagnoseRequest,
  IncidentDetail,
  Runbook,
} from "@/types";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  timeout: 120_000, // 2 min — LLM calls can be slow
});

// ── Runbooks ──────────────────────────────────────────────────────────────────

export async function uploadRunbook(file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/api/runbooks/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data as { success: boolean; runbook: Runbook; message: string };
}

export async function listRunbooks() {
  const { data } = await api.get("/api/runbooks");
  return data as { runbooks: Runbook[]; total: number };
}

export async function deleteRunbook(id: number) {
  const { data } = await api.delete(`/api/runbooks/${id}`);
  return data as { success: boolean; message: string };
}

// ── Incidents ─────────────────────────────────────────────────────────────────

export async function diagnoseIncident(req: DiagnoseRequest) {
  const { data } = await api.post("/api/incidents/diagnose", req);
  return data as IncidentDetail & { success: boolean };
}

export async function listIncidents() {
  const { data } = await api.get("/api/incidents");
  return data as { incidents: import("@/types").Incident[]; total: number };
}

export async function getIncident(id: number) {
  const { data } = await api.get(`/api/incidents/${id}`);
  return data as IncidentDetail;
}

export async function executeWorkflow(id: number) {
  const { data } = await api.post(`/api/incidents/${id}/execute`);
  return data as { success: boolean; message: string; websocket_url: string };
}

export async function confirmStep(incidentId: number, stepId: number, confirmed: boolean) {
  const { data } = await api.post(`/api/incidents/${incidentId}/confirm-step`, {
    step_id: stepId,
    confirmed,
  });
  return data as { success: boolean; step_id: number; confirmed: boolean };
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

export function createIncidentWebSocket(incidentId: number): WebSocket {
  const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
  return new WebSocket(`${wsBase}/ws/incidents/${incidentId}`);
}
