"use client";

import { useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  Brain,
  History,
  Play,
  ShieldAlert,
  Zap,
} from "lucide-react";

import type { IncidentDetail } from "@/types";
import { cn } from "@/lib/utils";
import RunbookManager from "@/components/panels/RunbookManager";
import IncidentReporter from "@/components/panels/IncidentReporter";
import DiagnosisPanel from "@/components/panels/DiagnosisPanel";
import WorkflowViewer from "@/components/panels/WorkflowViewer";
import EscalationPanel from "@/components/panels/EscalationPanel";
import IncidentHistory from "@/components/panels/IncidentHistory";

type Tab = "runbooks" | "report" | "diagnosis" | "workflow" | "escalation" | "history";

interface NavTab {
  id: Tab;
  label: string;
  icon: React.ReactNode;
  badge?: string;
}

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<Tab>("runbooks");
  const [currentIncident, setCurrentIncident] = useState<IncidentDetail | null>(null);

  function handleDiagnosed(result: IncidentDetail) {
    setCurrentIncident(result);
    setActiveTab("diagnosis");
  }

  function handleHistorySelect(detail: IncidentDetail) {
    setCurrentIncident(detail);
    setActiveTab("diagnosis");
  }

  const tabs: NavTab[] = [
    { id: "runbooks", label: "Runbooks", icon: <BookOpen className="w-4 h-4" /> },
    { id: "report", label: "New Incident", icon: <AlertTriangle className="w-4 h-4" /> },
    {
      id: "diagnosis",
      label: "Diagnosis",
      icon: <Brain className="w-4 h-4" />,
      badge: currentIncident ? `#${currentIncident.incident.id}` : undefined,
    },
    {
      id: "workflow",
      label: "Workflow",
      icon: <Play className="w-4 h-4" />,
      badge: currentIncident
        ? `${currentIncident.workflow_steps.length} steps`
        : undefined,
    },
    {
      id: "escalation",
      label: "Escalation",
      icon: <ShieldAlert className="w-4 h-4" />,
      badge: currentIncident?.escalation ? "!" : undefined,
    },
    { id: "history", label: "History", icon: <History className="w-4 h-4" /> },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Background gradient */}
      <div className="fixed inset-0 bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 pointer-events-none" />

      {/* Header */}
      <header className="relative z-10 border-b border-white/10 bg-black/20 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                <Zap className="w-4 h-4 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white tracking-tight">AURA</h1>
                <p className="text-xs text-slate-400 -mt-0.5">
                  Automated Unified Response Architecture
                </p>
              </div>
            </div>
            {currentIncident && (
              <div className="hidden sm:flex items-center gap-2 text-xs text-slate-400">
                <span>Active:</span>
                <span className="text-white font-medium">
                  {currentIncident.incident.title.slice(0, 40)}
                  {currentIncident.incident.title.length > 40 ? "…" : ""}
                </span>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <div className="flex gap-6">
          {/* Sidebar nav */}
          <nav className="hidden lg:flex flex-col gap-1 w-52 shrink-0">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                disabled={
                  (tab.id === "diagnosis" || tab.id === "workflow" || tab.id === "escalation") &&
                  !currentIncident
                }
                className={cn(
                  "flex items-center justify-between gap-2.5 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed text-left",
                  activeTab === tab.id
                    ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/20"
                    : "text-slate-400 hover:text-white hover:bg-white/5"
                )}
              >
                <span className="flex items-center gap-2.5">
                  {tab.icon}
                  {tab.label}
                </span>
                {tab.badge && (
                  <span className="text-xs bg-white/20 rounded-full px-1.5 py-0.5 font-mono">
                    {tab.badge}
                  </span>
                )}
              </button>
            ))}
          </nav>

          {/* Mobile tabs */}
          <div className="lg:hidden w-full mb-4">
            <div className="flex gap-1 overflow-x-auto pb-2 no-scrollbar">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  disabled={
                    (tab.id === "diagnosis" || tab.id === "workflow" || tab.id === "escalation") &&
                    !currentIncident
                  }
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap shrink-0 transition-colors disabled:opacity-30",
                    activeTab === tab.id
                      ? "bg-indigo-600 text-white"
                      : "text-slate-400 hover:text-white bg-white/5"
                  )}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Main content */}
          <main className="flex-1 min-w-0">
            {activeTab === "runbooks" && <RunbookManager />}

            {activeTab === "report" && (
              <IncidentReporter onDiagnosed={handleDiagnosed} />
            )}

            {activeTab === "diagnosis" && currentIncident && (
              <DiagnosisPanel incident={currentIncident.incident} />
            )}

            {activeTab === "workflow" && currentIncident && (
              <WorkflowViewer initialData={currentIncident} />
            )}

            {activeTab === "escalation" && currentIncident?.escalation && (
              <EscalationPanel escalation={currentIncident.escalation} />
            )}

            {activeTab === "escalation" && currentIncident && !currentIncident.escalation && (
              <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                <ShieldAlert className="w-12 h-12 mb-3 opacity-30" />
                <p className="text-sm">No escalation triggered for this incident.</p>
                <p className="text-xs mt-1 text-slate-600">
                  Escalation occurs when confidence &lt; 60% or severity is P1.
                </p>
              </div>
            )}

            {activeTab === "history" && (
              <IncidentHistory onSelect={handleHistorySelect} />
            )}

            {/* Placeholder for disabled tabs */}
            {(activeTab === "diagnosis" || activeTab === "workflow" || activeTab === "escalation") &&
              !currentIncident && (
                <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                  <Brain className="w-12 h-12 mb-3 opacity-30" />
                  <p className="text-sm">No active incident.</p>
                  <p className="text-xs mt-1 text-slate-600">
                    Report an incident to see diagnosis and workflow results.
                  </p>
                </div>
              )}
          </main>
        </div>
      </div>
    </div>
  );
}
