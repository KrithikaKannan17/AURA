import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { IncidentStatus, Severity, StepStatus } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function severityColor(severity: Severity) {
  return {
    P1: "bg-red-500/20 text-red-400 border-red-500/40",
    P2: "bg-orange-500/20 text-orange-400 border-orange-500/40",
    P3: "bg-yellow-500/20 text-yellow-400 border-yellow-500/40",
  }[severity];
}

export function incidentStatusColor(status: IncidentStatus) {
  const map: Record<IncidentStatus, string> = {
    open: "bg-slate-500/20 text-slate-300",
    diagnosing: "bg-blue-500/20 text-blue-400",
    workflow_ready: "bg-purple-500/20 text-purple-400",
    executing: "bg-cyan-500/20 text-cyan-400",
    resolved: "bg-green-500/20 text-green-400",
    escalated: "bg-red-500/20 text-red-400",
    failed: "bg-red-700/20 text-red-500",
  };
  return map[status] ?? "bg-slate-500/20 text-slate-300";
}

export function stepStatusColor(status: StepStatus) {
  const map: Record<StepStatus, string> = {
    pending: "text-slate-400",
    running: "text-cyan-400",
    done: "text-green-400",
    failed: "text-red-400",
    skipped: "text-slate-500",
    awaiting_confirmation: "text-yellow-400",
  };
  return map[status] ?? "text-slate-400";
}

export function stepStatusIcon(status: StepStatus) {
  const map: Record<StepStatus, string> = {
    pending: "○",
    running: "◉",
    done: "✓",
    failed: "✗",
    skipped: "⊘",
    awaiting_confirmation: "⚠",
  };
  return map[status] ?? "○";
}

export function confidenceLabel(score: number) {
  if (score >= 0.8) return { label: "High", color: "text-green-400" };
  if (score >= 0.6) return { label: "Medium", color: "text-yellow-400" };
  return { label: "Low", color: "text-red-400" };
}

export function formatDate(dateStr: string | null) {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleString();
}
