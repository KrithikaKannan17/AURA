"use client";

import { Brain, ChevronDown, ChevronUp, ExternalLink, FileText } from "lucide-react";
import { useState } from "react";

import { cn, confidenceLabel, severityColor } from "@/lib/utils";
import type { Incident, Source } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface Props {
  incident: Incident;
}

function SourceCard({ source, index }: { source: Source; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const pct = Math.round(source.relevance_score * 100);

  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-bold text-indigo-400 shrink-0">#{index + 1}</span>
          <div className="min-w-0">
            <p className="text-xs font-medium text-white truncate">
              {source.source_file}
            </p>
            <p className="text-xs text-slate-400 truncate">{source.section_title}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-slate-400">p.{source.page_number}</span>
          <div className="w-12">
            <div className="text-right text-xs text-indigo-300 font-medium mb-0.5">{pct}%</div>
            <Progress value={pct} barClassName="bg-indigo-500" className="h-1" />
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-slate-500 hover:text-white transition-colors"
          >
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>
      {expanded && (
        <p className="mt-2 text-xs text-slate-400 leading-relaxed border-t border-white/10 pt-2">
          {source.excerpt}
        </p>
      )}
    </div>
  );
}

export default function DiagnosisPanel({ incident }: Props) {
  const { label: confLabel, color: confColor } = confidenceLabel(
    incident.confidence_score ?? 0
  );
  const confPct = Math.round((incident.confidence_score ?? 0) * 100);

  const confBarClass =
    confPct >= 60 ? "bg-green-500" : confPct >= 40 ? "bg-yellow-500" : "bg-red-500";

  return (
    <div className="space-y-5">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-indigo-400" />
              Diagnosis — Incident #{incident.id}
            </CardTitle>
            <Badge className={cn("border", severityColor(incident.severity))}>
              {incident.severity}
            </Badge>
          </div>
          <p className="text-sm text-slate-400 mt-1 line-clamp-2">{incident.title}</p>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Confidence */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-slate-400">AI Confidence</span>
              <span className={cn("text-sm font-bold", confColor)}>
                {confLabel} — {confPct}%
              </span>
            </div>
            <Progress value={confPct} barClassName={confBarClass} />
          </div>

          {/* Root Cause */}
          <div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
              Root Cause
            </p>
            <div className="rounded-lg bg-white/5 border border-white/10 p-3">
              <p className="text-sm text-white leading-relaxed">
                {incident.root_cause ?? "Analysis in progress…"}
              </p>
            </div>
          </div>

          {/* System */}
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span>
              System: <span className="text-white">{incident.system_affected}</span>
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Remediation Steps */}
      {incident.remediation_steps && incident.remediation_steps.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Remediation Steps</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2.5">
              {incident.remediation_steps.map((step, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="shrink-0 w-5 h-5 rounded-full bg-indigo-500/20 text-indigo-400 text-xs font-bold flex items-center justify-center">
                    {i + 1}
                  </span>
                  <span className={cn(
                    "text-slate-200 leading-relaxed",
                    step.includes("[REQUIRES CONFIRMATION]") && "text-yellow-300"
                  )}>
                    {step}
                  </span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {/* Sources */}
      {incident.sources && incident.sources.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <FileText className="w-4 h-4 text-slate-400" />
              Runbook Sources Cited ({incident.sources.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {incident.sources.map((source, i) => (
                <SourceCard key={i} source={source} index={i} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
