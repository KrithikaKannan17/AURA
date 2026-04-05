"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRight, History, Loader2 } from "lucide-react";

import { getIncident, listIncidents } from "@/lib/api";
import {
  cn,
  formatDate,
  incidentStatusColor,
  severityColor,
} from "@/lib/utils";
import type { Incident, IncidentDetail } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  onSelect: (detail: IncidentDetail) => void;
}

export default function IncidentHistory({ onSelect }: Props) {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [selecting, setSelecting] = useState<number | null>(null);

  const fetchIncidents = useCallback(async () => {
    try {
      const data = await listIncidents();
      setIncidents(data.incidents);
    } catch {
      // silently fail — user can refresh
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIncidents();
    const interval = setInterval(fetchIncidents, 10_000);
    return () => clearInterval(interval);
  }, [fetchIncidents]);

  async function handleSelect(id: number) {
    setSelecting(id);
    try {
      const detail = await getIncident(id);
      onSelect(detail);
    } catch {
      // ignore
    } finally {
      setSelecting(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="w-4 h-4 text-slate-400" />
          Incident History
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
          </div>
        ) : incidents.length === 0 ? (
          <div className="text-center py-10 text-slate-500 text-sm">
            No incidents yet.
          </div>
        ) : (
          <ul className="divide-y divide-white/5">
            {incidents.map((inc) => (
              <li key={inc.id}>
                <button
                  onClick={() => handleSelect(inc.id)}
                  className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-white/5 transition-colors text-left"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-xs text-slate-500 font-mono">#{inc.id}</span>
                      <Badge className={cn("border text-xs", severityColor(inc.severity))}>
                        {inc.severity}
                      </Badge>
                      <Badge className={cn("text-xs", incidentStatusColor(inc.status))}>
                        {inc.status.replace("_", " ")}
                      </Badge>
                    </div>
                    <p className="text-sm text-white truncate">{inc.title}</p>
                    <p className="text-xs text-slate-500 mt-0.5 truncate">{inc.system_affected}</p>
                    <p className="text-xs text-slate-600 mt-0.5">{formatDate(inc.created_at)}</p>
                  </div>
                  <div className="shrink-0">
                    {selecting === inc.id ? (
                      <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />
                    ) : (
                      <ArrowRight className="w-4 h-4 text-slate-500" />
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
