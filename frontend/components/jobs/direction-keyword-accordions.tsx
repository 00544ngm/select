"use client";

import { useState } from "react";
import { Copy, ExternalLink } from "lucide-react";
import { amazonSearchUrl, normalizeDirectionKeywords } from "@/lib/direction-keywords";

type CopyState = "idle" | "copied" | "failed";

function copyLabel(state: CopyState, idleLabel: string): string {
  if (state === "copied") return "已复制";
  if (state === "failed") return "复制失败，请手动复制";
  return idleLabel;
}

export default function DirectionKeywordAccordions({ keywords }: { keywords: unknown }) {
  const normalized = normalizeDirectionKeywords(keywords);
  const [amazonCopyState, setAmazonCopyState] = useState<CopyState>("idle");
  const [englishCopyState, setEnglishCopyState] = useState<CopyState>("idle");

  const copyKeyword = async (
    value: string,
    setState: (state: CopyState) => void
  ) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setState("copied");
    } catch {
      setState("failed");
    }
  };

  return (
    <section className="space-y-2 py-4" aria-label="建议检索关键词">
      <details open className="border bg-background">
        <summary className="cursor-pointer px-3 py-3 text-sm font-semibold">
          Amazon 精准关键词
        </summary>
        <div className="border-t p-3">
          <p className="keyword-text break-words border bg-muted/30 px-3 py-2">
            {normalized.amazon || "暂无可用关键词"}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              aria-label="复制精准词"
              disabled={!normalized.amazon}
              onClick={() => copyKeyword(normalized.amazon, setAmazonCopyState)}
              className="inline-flex items-center gap-2 border px-3 py-2 text-sm disabled:opacity-50"
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
              {copyLabel(amazonCopyState, "复制精准词")}
            </button>
            <a
              aria-label="打开 Amazon 搜索"
              href={normalized.amazon ? amazonSearchUrl(normalized.amazon) : undefined}
              target="_blank"
              rel="noreferrer"
              aria-disabled={!normalized.amazon}
              className="inline-flex items-center gap-2 border px-3 py-2 text-sm aria-disabled:pointer-events-none aria-disabled:opacity-50"
            >
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
              打开 Amazon 搜索
            </a>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            模型建议的精准检索入口，不代表 Amazon 已验证销量、相关性或具体商品可用性。
          </p>
        </div>
      </details>
      <details className="border bg-background">
        <summary className="cursor-pointer px-3 py-3 text-sm font-semibold">
          英文通用关键词
        </summary>
        <div className="border-t p-3">
          <p className="keyword-text break-words border bg-muted/30 px-3 py-2">
            {normalized.en || "暂无可用关键词"}
          </p>
          <button
            type="button"
            aria-label="复制通用词"
            disabled={!normalized.en}
            onClick={() => copyKeyword(normalized.en, setEnglishCopyState)}
            className="mt-3 inline-flex items-center gap-2 border px-3 py-2 text-sm disabled:opacity-50"
          >
            <Copy className="h-4 w-4" aria-hidden="true" />
            {copyLabel(englishCopyState, "复制通用词")}
          </button>
        </div>
      </details>
    </section>
  );
}
