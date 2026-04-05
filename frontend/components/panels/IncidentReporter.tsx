"use client";

import { useState } from "react";
import { AlertTriangle, Send, Zap } from "lucide-react";
import { toast } from "sonner";

import { diagnoseIncident } from "@/lib/api";
import { cn, severityColor } from "@/lib/utils";
import type { IncidentDetail, Severity } from "@/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const SYSTEMS = [
  "API Gateway",
  "Authentication Service",
  "Database (PostgreSQL)",
  "Database (MySQL)",
  "Kubernetes Cluster",
  "Message Queue (Kafka)",
  "Cache (Redis)",
  "CDN / Load Balancer",
  "Payment Service",
  "Notification Service",
  "Storage (S3)",
  "Other",
];

const SEVERITY_OPTIONS: { value: Severity; label: string; desc: string }[] = [
  { value: "P1", label: "P1 — Critical", desc: "Full outage, revenue impact" },
  { value: "P2", label: "P2 — High", desc: "Major degradation" },
  { value: "P3", label: "P3 — Medium", desc: "Partial impact / degraded" },
];

interface Props {
  onDiagnosed: (result: IncidentDetail) => void;
}

export default function IncidentReporter({ onDiagnosed }: Props) {
  const [form, setForm] = useState({
    title: "",
    description: "",
    severity: "P2" as Severity,
    system_affected: "API Gateway",
  });
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (form.description.length < 10) {
      toast.error("Please provide a more detailed incident description.");
      return;
    }
    setLoading(true);
    try {
      const result = await diagnoseIncident({
        incident_description: form.description,
        severity: form.severity,
        system_affected: form.system_affected,
        title: form.title || undefined,
      });
      toast.success(`Incident #${result.incident.id} diagnosed!`);
      onDiagnosed(result);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Diagnosis pipeline failed.";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-orange-400" />
          Report Incident
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Title */}
          <div>
            <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Incident Title (optional)
            </label>
            <input
              type="text"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="e.g. Database connection pool exhausted in prod"
              className="mt-1.5 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition"
            />
          </div>

          {/* Description */}
          <div>
            <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Incident Description <span className="text-red-400">*</span>
            </label>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              required
              rows={5}
              placeholder="Describe the incident in detail: what's happening, error messages, when it started, what you've already tried..."
              className="mt-1.5 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition resize-none"
            />
          </div>

          {/* Severity */}
          <div>
            <label className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2 block">
              Severity <span className="text-red-400">*</span>
            </label>
            <div className="grid grid-cols-3 gap-2">
              {SEVERITY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setForm({ ...form, severity: opt.value })}
                  className={cn(
                    "rounded-lg border px-3 py-2.5 text-left transition-all duration-200",
                    form.severity === opt.value
                      ? cn("border-current", severityColor(opt.value))
                      : "border-white/10 text-slate-400 hover:border-white/20"
                  )}
                >
                  <p className="text-xs font-bold">{opt.label}</p>
                  <p className="text-xs opacity-70 mt-0.5">{opt.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* System Affected */}
          <div>
            <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              System Affected <span className="text-red-400">*</span>
            </label>
            <select
              value={form.system_affected}
              onChange={(e) => setForm({ ...form, system_affected: e.target.value })}
              className="mt-1.5 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition appearance-none cursor-pointer"
            >
              {SYSTEMS.map((s) => (
                <option key={s} value={s} className="bg-slate-900">
                  {s}
                </option>
              ))}
            </select>
          </div>

          {/* Submit */}
          <Button
            type="submit"
            variant="primary"
            size="lg"
            loading={loading}
            className="w-full justify-center"
          >
            {loading ? (
              "Running AI Diagnosis…"
            ) : (
              <>
                <Zap className="w-4 h-4" />
                Run AI Diagnosis
              </>
            )}
          </Button>

          {loading && (
            <div className="rounded-lg bg-indigo-500/10 border border-indigo-500/20 p-3 text-xs text-indigo-300 text-center">
              <Send className="w-3.5 h-3.5 inline mr-1.5" />
              Running multi-agent pipeline: Diagnosis → Workflow → Escalation…
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
