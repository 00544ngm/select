"use client";

import { type UseFormRegisterReturn } from "react-hook-form";

interface UrlFieldProps {
  placeholder?: string;
  registration: UseFormRegisterReturn;
  error?: string;
  onRemove?: () => void;
}

export default function UrlField({
  placeholder = "请输入商品链接",
  registration,
  error,
  onRemove,
}: UrlFieldProps) {
  return (
    <div className="flex items-start gap-2">
      <div className="flex-1">
        <input
          type="url"
          placeholder={placeholder}
          className={`h-10 w-full rounded-md border bg-background px-3 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ring ${
            error ? "border-destructive" : "border-input"
          }`}
          aria-invalid={!!error}
          {...registration}
        />
        {error && (
          <p className="mt-1 text-xs text-destructive" role="alert">
            {error}
          </p>
        )}
      </div>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="flex h-10 w-10 items-center justify-center rounded-md text-muted-foreground hover:bg-muted"
          aria-label="删除"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 6h18" />
            <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
          </svg>
        </button>
      )}
    </div>
  );
}
