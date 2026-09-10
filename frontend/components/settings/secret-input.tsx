"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff, KeyRound, X } from "lucide-react";

interface SecretInputProps {
  maskedValue: string | null;
  value?: string;
  onChange: (value: string | undefined) => void;
}

export default function SecretInput({ maskedValue, value, onChange }: SecretInputProps) {
  const [replacing, setReplacing] = useState(!maskedValue);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (maskedValue) {
      setReplacing(false);
      setVisible(false);
    }
  }, [maskedValue]);

  if (!replacing && maskedValue) {
    return (
      <div className="flex min-h-10 items-center justify-between gap-3 rounded-md border border-input bg-background px-3">
        <span className="inline-flex min-w-0 items-center gap-2 font-mono text-sm">
          <KeyRound className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="truncate">{maskedValue}</span>
        </span>
        <button
          type="button"
          className="shrink-0 text-xs font-medium text-primary hover:underline"
          onClick={() => {
            setReplacing(true);
            onChange("");
          }}
        >
          替换密钥
        </button>
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      <div className="relative min-w-0 flex-1">
        <input
          aria-label="新 API Key"
          type={visible ? "text" : "password"}
          autoComplete="new-password"
          value={value ?? ""}
          onChange={(event) => onChange(event.target.value)}
          placeholder="输入新的 API Key"
          className="h-10 w-full rounded-md border border-input bg-background px-3 pr-10 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          type="button"
          aria-label={visible ? "隐藏 API Key" : "显示 API Key"}
          title={visible ? "隐藏 API Key" : "显示 API Key"}
          onClick={() => setVisible((current) => !current)}
          className="absolute right-1 top-1 flex h-8 w-8 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {maskedValue && (
        <button
          type="button"
          aria-label="取消替换密钥"
          title="取消替换密钥"
          onClick={() => {
            setReplacing(false);
            setVisible(false);
            onChange(undefined);
          }}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-input text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

