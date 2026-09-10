"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Pencil, X } from "lucide-react";

interface JobNameEditorProps {
  name: string | null;
  editing: boolean;
  saving: boolean;
  error?: string;
  onStart: () => void;
  onSave: (name: string | null) => void;
  onCancel: () => void;
}

export default function JobNameEditor({
  name,
  editing,
  saving,
  error,
  onStart,
  onSave,
  onCancel,
}: JobNameEditorProps) {
  const [draft, setDraft] = useState(name ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) return;
    setDraft(name ?? "");
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  }, [editing, name]);

  if (!editing) {
    return (
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="block min-w-0 truncate text-sm font-medium">
          {name || "未命名任务"}
        </span>
        <button
          type="button"
          onClick={onStart}
          aria-label="修改任务备注"
          className="shrink-0 p-1 text-muted-foreground hover:text-foreground"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  const submit = () => onSave(draft.trim() || null);

  return (
    <div className="space-y-1.5">
      <div className="flex min-w-0 items-center gap-1.5">
        <input
          ref={inputRef}
          aria-label="任务备注"
          value={draft}
          maxLength={100}
          disabled={saving}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              submit();
            } else if (event.key === "Escape") {
              event.preventDefault();
              onCancel();
            }
          }}
          className="h-8 min-w-0 flex-1 border bg-background px-2 text-sm outline-none focus:border-primary disabled:opacity-60"
        />
        <button
          type="button"
          onClick={submit}
          disabled={saving}
          aria-label="保存任务备注"
          className="grid h-8 w-8 shrink-0 place-items-center border text-primary disabled:opacity-50"
        >
          <Check className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          aria-label="取消修改"
          className="grid h-8 w-8 shrink-0 place-items-center border text-muted-foreground disabled:opacity-50"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
