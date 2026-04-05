"use client";

import {
  AlertOctagon,
  Bell,
  CheckCircle2,
  Loader2,
  MessageSquare,
  XCircle,
} from "lucide-react";

import { cn, formatDate } from "@/lib/utils";
import type { Escalation } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type DeliveryStatus = "sent" | "failed" | "pending" | "skipped";

function DeliveryBadge({
  status,
  label,
}: {
  status: DeliveryStatus;
  label: string;
}) {
  if (status === "sent")
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-green-400">
        <CheckCircle2 className="w-3.5 h-3.5" />
        {label} Delivered
      </span>
    );
  if (status === "failed")
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-red-400">
        <XCircle className="w-3.5 h-3.5" />
        {label} Failed
      </span>
    );
  if (status === "pending")
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-yellow-400">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        {label} Pending
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
      {label} Skipped
    </span>
  );
}

function ReasonBadge({ reason }: { reason: string }) {
  const labels: Record<string, { label: string; className: string }> = {
    p1_severity: { label: "P1 Severity", className: "bg-red-500/20 text-red-400 border-red-500/40" },
    low_confidence: { label: "Low Confidence", className: "bg-orange-500/20 text-orange-400 border-orange-500/40" },
    execution_failure: { label: "Execution Failure", className: "bg-red-600/20 text-red-500 border-red-600/40" },
    not_needed: { label: "Not Required", className: "bg-slate-500/20 text-slate-400 border-slate-500/40" },
  };

  // Reason can be a combined string like "low_confidence + p1_severity"
  const parts = reason.split("+").map((p) => p.trim());
  return (
    <div className="flex flex-wrap gap-1.5">
      {parts.map((part) => {
        const match = Object.entries(labels).find(([key]) => part.includes(key));
        if (match) {
          const [, cfg] = match;
          return (
            <Badge key={part} className={cn("border text-xs", cfg.className)}>
              {cfg.label}
            </Badge>
          );
        }
        return (
          <Badge key={part} className="bg-slate-500/20 text-slate-400 border-slate-500/40 text-xs">
            {part}
          </Badge>
        );
      })}
    </div>
  );
}

interface Props {
  escalation: Escalation;
}

export default function EscalationPanel({ escalation }: Props) {
  return (
    <div className="space-y-5">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <AlertOctagon className="w-4 h-4 text-red-400" />
              Escalation Report
            </CardTitle>
            <span className="text-xs text-slate-400">{formatDate(escalation.created_at)}</span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Escalation Reason */}
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">Reason</p>
            <ReasonBadge reason={escalation.reason} />
          </div>

          {/* Summary */}
          {escalation.summary && (
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">
                Incident Summary
              </p>
              <div className="rounded-lg bg-white/5 border border-white/10 p-3">
                <p className="text-sm text-white leading-relaxed">{escalation.summary}</p>
              </div>
            </div>
          )}

          {/* Failure Reason */}
          {escalation.failure_reason && (
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">
                Why Escalated
              </p>
              <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3">
                <p className="text-sm text-red-200 leading-relaxed">
                  {escalation.failure_reason}
                </p>
              </div>
            </div>
          )}

          {/* Recommended Action */}
          {escalation.recommended_action && (
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">
                Recommended On-Call Action
              </p>
              <div className="rounded-lg bg-yellow-500/10 border border-yellow-500/20 p-3">
                <p className="text-sm text-yellow-200 leading-relaxed">
                  {escalation.recommended_action}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Webhook Delivery Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Bell className="w-4 h-4 text-indigo-400" />
            Webhook Delivery Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            {/* Slack */}
            <div className="rounded-lg bg-white/5 border border-white/10 p-4">
              <div className="flex items-center gap-2 mb-3">
                <MessageSquare className="w-5 h-5 text-[#4A154B]" />
                <span className="text-sm font-medium text-white">Slack</span>
              </div>
              <DeliveryBadge
                status={escalation.slack_status as DeliveryStatus}
                label="Slack"
              />
              {escalation.slack_status === "sent" && (
                <div className="mt-2 text-xs text-slate-400 rounded bg-black/20 p-2">
                  Mock webhook delivered ✓
                </div>
              )}
            </div>

            {/* PagerDuty */}
            <div className="rounded-lg bg-white/5 border border-white/10 p-4">
              <div className="flex items-center gap-2 mb-3">
                <AlertOctagon className="w-5 h-5 text-[#06AC38]" />
                <span className="text-sm font-medium text-white">PagerDuty</span>
              </div>
              <DeliveryBadge
                status={escalation.pagerduty_status as DeliveryStatus}
                label="PagerDuty"
              />
              {escalation.pagerduty_status === "sent" && (
                <div className="mt-2 text-xs text-slate-400 rounded bg-black/20 p-2">
                  Mock event triggered ✓
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
