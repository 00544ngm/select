"use client";

import { FileDown, FileSpreadsheet } from "lucide-react";
import { downloadArtifact } from "@/lib/api/jobs";

interface ArtifactActionsProps {
  jobId: string;
  activeModel?: string;
  compact?: boolean;
}

export default function ArtifactActions({ jobId, activeModel, compact }: ArtifactActionsProps) {
  const handleDownload = async (kind: "json" | "excel") => {
    // Primary model (gpt) uses base kind; secondary model uses _{model} suffix
    const artifactKind = activeModel && activeModel !== "gpt" ? `${kind}_${activeModel}` : kind;
    try {
      const blob = await downloadArtifact(jobId, artifactKind);
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `${jobId}_${activeModel ?? "gpt"}.${kind === "json" ? "json" : "xlsx"}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
    } catch {
      // Download failed silently
    }
  };

  if (compact) {
    return (
      <div className="flex shrink-0 gap-1">
        <button
          type="button"
          onClick={() => handleDownload("json")}
          aria-label="下载 JSON"
          title="下载 JSON"
          className="flex h-8 w-8 items-center justify-center rounded-md border transition-colors hover:bg-muted"
        >
          <FileDown className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => handleDownload("excel")}
          aria-label="下载 Excel"
          title="下载 Excel"
          className="flex h-8 w-8 items-center justify-center rounded-md border transition-colors hover:bg-muted"
        >
          <FileSpreadsheet className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={() => handleDownload("json")}
        className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-muted"
      >
        <FileDown className="h-4 w-4" />
        下载 JSON
      </button>
      <button
        type="button"
        onClick={() => handleDownload("excel")}
        className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-muted"
      >
        <FileSpreadsheet className="h-4 w-4" />
        下载 Excel
      </button>
    </div>
  );
}
