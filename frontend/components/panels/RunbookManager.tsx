"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  BookOpen,
  CheckCircle2,
  FileText,
  Loader2,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { deleteRunbook, listRunbooks, uploadRunbook } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";
import type { Runbook } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function RunbookManager() {
  const [runbooks, setRunbooks] = useState<Runbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchRunbooks = useCallback(async () => {
    try {
      const data = await listRunbooks();
      setRunbooks(data.runbooks);
    } catch {
      toast.error("Failed to load runbooks.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRunbooks();
  }, [fetchRunbooks]);

  async function handleUpload(file: File) {
    if (![".pdf", ".md"].some((ext) => file.name.toLowerCase().endsWith(ext))) {
      toast.error("Only PDF and Markdown files are supported.");
      return;
    }
    setUploading(true);
    try {
      const result = await uploadRunbook(file);
      toast.success(`"${file.name}" indexed — ${result.runbook.chunk_count} chunks`);
      await fetchRunbooks();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Upload failed.";
      toast.error(msg);
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  }

  async function handleDelete(id: number, name: string) {
    if (!confirm(`Delete "${name}"? This will remove all embeddings.`)) return;
    try {
      await deleteRunbook(id);
      toast.success(`"${name}" deleted.`);
      setRunbooks((prev) => prev.filter((r) => r.id !== id));
    } catch {
      toast.error("Failed to delete runbook.");
    }
  }

  function statusBadge(status: Runbook["status"]) {
    if (status === "indexed")
      return (
        <span className="inline-flex items-center gap-1 text-xs text-green-400">
          <CheckCircle2 className="w-3 h-3" /> Indexed
        </span>
      );
    if (status === "processing")
      return (
        <span className="inline-flex items-center gap-1 text-xs text-yellow-400">
          <Loader2 className="w-3 h-3 animate-spin" /> Processing
        </span>
      );
    return (
      <span className="inline-flex items-center gap-1 text-xs text-red-400">
        <XCircle className="w-3 h-3" /> Failed
      </span>
    );
  }

  return (
    <div className="space-y-6">
      {/* Drop Zone */}
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "relative border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all duration-200",
          dragging
            ? "border-indigo-400 bg-indigo-500/10"
            : "border-white/20 hover:border-indigo-400/60 hover:bg-white/5"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.md"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleUpload(file);
            e.target.value = "";
          }}
        />
        <div className="flex flex-col items-center gap-3">
          {uploading ? (
            <Loader2 className="w-10 h-10 text-indigo-400 animate-spin" />
          ) : (
            <Upload className="w-10 h-10 text-slate-400" />
          )}
          <div>
            <p className="text-sm font-medium text-white">
              {uploading ? "Uploading and indexing…" : "Drop your runbook here"}
            </p>
            <p className="text-xs text-slate-400 mt-1">PDF or Markdown — click to browse</p>
          </div>
        </div>
      </div>

      {/* Runbook List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-indigo-400" />
              Indexed Runbooks
            </CardTitle>
            <Badge className="bg-indigo-500/20 text-indigo-300 border-indigo-500/40">
              {runbooks.length} total
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
            </div>
          ) : runbooks.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <FileText className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-sm">No runbooks indexed yet.</p>
            </div>
          ) : (
            <ul className="divide-y divide-white/5">
              {runbooks.map((rb) => (
                <li
                  key={rb.id}
                  className="flex items-center justify-between px-5 py-3.5 hover:bg-white/5 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <FileText className="w-4 h-4 text-slate-400 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm text-white truncate font-medium">
                        {rb.original_filename}
                      </p>
                      <p className="text-xs text-slate-500">
                        {rb.chunk_count} chunks · {formatDate(rb.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 ml-4">
                    {statusBadge(rb.status)}
                    <Badge variant="outline" className="text-slate-400 border-white/10 text-xs">
                      {rb.file_type.toUpperCase()}
                    </Badge>
                    <button
                      onClick={() => handleDelete(rb.id, rb.original_filename)}
                      className="text-slate-500 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
