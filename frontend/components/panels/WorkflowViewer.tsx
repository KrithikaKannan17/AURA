"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDot,
  Clock,
  Play,
  RefreshCw,
  SkipForward,
  Terminal,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { confirmStep, executeWorkflow, getIncident, createIncidentWebSocket } from "@/lib/api";
import { cn, formatDate, stepStatusColor } from "@/lib/utils";
import type { IncidentDetail, StepStatus, WorkflowStep, WsMessage } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STATUS_ICON: Record<StepStatus, React.ReactNode> = {
  pending: <Clock className="w-4 h-4 text-slate-500" />,
  running: <CircleDot className="w-4 h-4 text-cyan-400 animate-pulse" />,
  done: <CheckCircle2 className="w-4 h-4 text-green-400" />,
  failed: <XCircle className="w-4 h-4 text-red-400" />,
  skipped: <SkipForward className="w-4 h-4 text-slate-500" />,
  awaiting_confirmation: <AlertTriangle className="w-4 h-4 text-yellow-400 animate-pulse" />,
};

interface StepCardProps {
  step: WorkflowStep;
  onConfirm: (stepId: number, confirmed: boolean) => void;
}

function StepCard({ step, onConfirm }: StepCardProps) {
  const [expanded, setExpanded] = useState(
    step.status === "running" || step.status === "awaiting_confirmation"
  );

  useEffect(() => {
    if (step.status === "running" || step.status === "awaiting_confirmation" || step.status === "failed") {
      setExpanded(true);
    }
  }, [step.status]);

  const statusClass = stepStatusColor(step.status);

  return (
    <div
      className={cn(
        "rounded-xl border transition-all duration-300",
        step.status === "running" && "border-cyan-500/40 bg-cyan-500/5",
        step.status === "done" && "border-green-500/30 bg-green-500/5",
        step.status === "failed" && "border-red-500/40 bg-red-500/5",
        step.status === "awaiting_confirmation" && "border-yellow-500/40 bg-yellow-500/5",
        step.status === "pending" && "border-white/10 bg-white/3",
        step.status === "skipped" && "border-white/5 bg-transparent opacity-60",
      )}
    >
      <div
        className="flex items-center gap-3 p-4 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="shrink-0">{STATUS_ICON[step.status]}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-slate-500">Step {step.step_id}</span>
            {step.is_destructive && (
              <Badge className="bg-red-500/20 text-red-400 border-red-500/40 text-xs">
                Destructive
              </Badge>
            )}
            {step.requires_confirmation && step.status !== "done" && step.status !== "skipped" && (
              <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/40 text-xs">
                Needs Confirmation
              </Badge>
            )}
          </div>
          <p className={cn("text-sm font-medium mt-0.5", statusClass)}>{step.action}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={cn("text-xs capitalize", statusClass)}>{step.status.replace("_", " ")}</span>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-slate-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-500" />
          )}
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/10 pt-3">
          {step.command && (
            <div>
              <p className="text-xs text-slate-500 mb-1 flex items-center gap-1.5">
                <Terminal className="w-3 h-3" /> Command
              </p>
              <code className="block rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-xs text-green-300 font-mono whitespace-pre-wrap break-all">
                {step.command}
              </code>
            </div>
          )}

          {step.expected_outcome && (
            <div>
              <p className="text-xs text-slate-500 mb-1">Expected Outcome</p>
              <p className="text-xs text-slate-300">{step.expected_outcome}</p>
            </div>
          )}

          {step.rollback && (
            <div>
              <p className="text-xs text-slate-500 mb-1">Rollback Command</p>
              <code className="block rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-xs text-orange-300 font-mono whitespace-pre-wrap break-all">
                {step.rollback}
              </code>
            </div>
          )}

          {step.output && (
            <div>
              <p className="text-xs text-slate-500 mb-1">Output</p>
              <pre className="text-xs text-slate-300 bg-black/30 rounded p-2 overflow-auto max-h-32">
                {step.output}
              </pre>
            </div>
          )}

          {step.started_at && (
            <p className="text-xs text-slate-500">
              Started: {formatDate(step.started_at)}
              {step.completed_at && ` · Completed: ${formatDate(step.completed_at)}`}
            </p>
          )}

          {step.status === "awaiting_confirmation" && (
            <div className="flex gap-2 pt-1">
              <Button
                size="sm"
                variant="danger"
                onClick={() => onConfirm(step.step_id, false)}
                className="flex-1 justify-center"
              >
                Skip This Step
              </Button>
              <Button
                size="sm"
                variant="primary"
                onClick={() => onConfirm(step.step_id, true)}
                className="flex-1 justify-center"
              >
                Confirm &amp; Execute
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface Props {
  initialData: IncidentDetail;
}

export default function WorkflowViewer({ initialData }: Props) {
  const [steps, setSteps] = useState<WorkflowStep[]>(initialData.workflow_steps);
  const [incidentStatus, setIncidentStatus] = useState(initialData.incident.status);
  const [executing, setExecuting] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const incidentId = initialData.incident.id;

  const updateStep = useCallback((stepId: number, patch: Partial<WorkflowStep>) => {
    setSteps((prev) =>
      prev.map((s) => (s.step_id === stepId ? { ...s, ...patch } : s))
    );
  }, []);

  const connectWs = useCallback(() => {
    if (wsRef.current) wsRef.current.close();
    const ws = createIncidentWebSocket(incidentId);
    wsRef.current = ws;

    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);

    ws.onmessage = (event) => {
      const msg: WsMessage = JSON.parse(event.data);

      if (msg.type === "initial_state" && msg.steps) {
        setSteps(msg.steps);
      } else if (msg.type === "step_update" && msg.step_id !== undefined) {
        updateStep(msg.step_id, {
          status: msg.status as StepStatus,
          output: msg.output,
        });
      } else if (msg.type === "execution_complete") {
        setIncidentStatus("resolved");
        setExecuting(false);
        toast.success("All workflow steps completed successfully!");
      } else if (msg.type === "error") {
        toast.error(msg.message ?? "Execution error");
        setExecuting(false);
      }
    };

    // Ping every 20s
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 20_000);

    ws.onclose = () => {
      setWsConnected(false);
      clearInterval(ping);
    };

    return () => { ws.close(); clearInterval(ping); };
  }, [incidentId, updateStep]);

  useEffect(() => {
    const cleanup = connectWs();
    return cleanup;
  }, [connectWs]);

  async function handleExecute() {
    setExecuting(true);
    try {
      await executeWorkflow(incidentId);
      setIncidentStatus("executing");
      toast.info("Workflow execution started.");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Failed to start execution.";
      toast.error(msg);
      setExecuting(false);
    }
  }

  async function handleConfirm(stepId: number, confirmed: boolean) {
    try {
      await confirmStep(incidentId, stepId, confirmed);
      updateStep(stepId, { status: confirmed ? "pending" : "skipped" });
      toast.success(confirmed ? "Step confirmed — executing…" : "Step skipped.");
    } catch {
      toast.error("Failed to update step confirmation.");
    }
  }

  async function handleRefresh() {
    try {
      const data = await getIncident(incidentId);
      setSteps(data.workflow_steps);
      setIncidentStatus(data.incident.status);
    } catch {
      toast.error("Failed to refresh.");
    }
  }

  const doneCount = steps.filter((s) => s.status === "done").length;
  const progress = steps.length > 0 ? Math.round((doneCount / steps.length) * 100) : 0;

  const canExecute = !executing &&
    incidentStatus !== "executing" &&
    incidentStatus !== "resolved";

  return (
    <div className="space-y-5">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Play className="w-4 h-4 text-cyan-400" />
              Workflow Execution
            </CardTitle>
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "w-2 h-2 rounded-full",
                  wsConnected ? "bg-green-400" : "bg-slate-500"
                )}
                title={wsConnected ? "WebSocket connected" : "WebSocket disconnected"}
              />
              <button
                onClick={handleRefresh}
                className="text-slate-500 hover:text-white transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Progress */}
          <div>
            <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
              <span>{doneCount}/{steps.length} steps completed</span>
              <span className="font-medium text-white">{progress}%</span>
            </div>
            <div className="w-full bg-white/10 rounded-full h-2 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-500 transition-all duration-700"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {canExecute && steps.length > 0 && (
            <Button
              onClick={handleExecute}
              loading={executing}
              className="w-full justify-center"
              variant="primary"
            >
              <Play className="w-4 h-4" />
              {executing ? "Executing…" : "Execute Workflow"}
            </Button>
          )}

          {incidentStatus === "resolved" && (
            <div className="flex items-center gap-2 text-green-400 bg-green-500/10 rounded-lg px-3 py-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span className="text-sm font-medium">Incident resolved successfully</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Step List */}
      {steps.length === 0 ? (
        <div className="text-center text-slate-500 py-10">
          <Terminal className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No workflow steps generated yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {steps.map((step) => (
            <StepCard key={step.id} step={step} onConfirm={handleConfirm} />
          ))}
        </div>
      )}
    </div>
  );
}
