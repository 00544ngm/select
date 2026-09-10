"use client";

import { useEffect } from "react";
import { X, Copy, Search, Scale, PackageCheck } from "lucide-react";
import FieldGrid from "@/components/jobs/field-grid";
import { cleanLabel, parseFmtText, pickField, scoreTone } from "@/lib/result-format";
import type { StructuredDirection } from "@/lib/api/types";
import { evidenceLevelLabel, formatStrategy, relationLabel } from "@/lib/result-labels";

interface Section {
  title: string;
  content?: string;
  children?: Section[];
}

interface DirectionDrawerProps {
  dir: StructuredDirection;
  sections?: Section[];
  onClose: () => void;
}

/**
 * 方向详情抽屉：点击方向卡片后从右侧滑出。
 * 展示 头部徽章 + 动机证据 + 深度论证 + 成本三卡 + 交付清单。
 */
export default function DirectionDrawer({ dir, sections, onClose }: DirectionDrawerProps) {
  // Esc 关闭 + 锁定背景滚动
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  // 在「假设方向」章节里找到本方向的详情节点
  const dirSection = sections
    ?.find((s) => s.title === "假设方向")
    ?.children?.find(
      (c) =>
        cleanLabel(c.title).includes(dir.name) ||
        dir.name.includes(cleanLabel(c.title).replace(/^方向\d+[:：]\s*/, ""))
    );

  const headerFields = parseFmtText(dirSection?.content);
  const motivation = pickField(headerFields, "动机");
  const deepArgs = dirSection?.children?.find((c) => cleanLabel(c.title) === "深度论证");
  const delivery = dirSection?.children?.find((c) => cleanLabel(c.title) === "交付清单");

  const tone = scoreTone(dir.score);

  const copyInfo = () => {
    const lines = [
      dir.name,
      `评分: ${dir.score ?? "-"}`,
      dir.type && `类型: ${relationLabel(dir.type)}`,
      dir.motivation && `动机: ${cleanLabel(dir.motivation)}`,
      dir.evidence_level && `证据级: ${evidenceLevelLabel(dir.evidence_level)}`,
      dir.cost && `1688成本: ${cleanLabel(dir.cost)}`,
      dir.strategy && `定价策略: ${formatStrategy(dir.strategy)}`,
    ].filter(Boolean);
    navigator.clipboard?.writeText(lines.join("\n")).catch(() => {});
  };

  return (
    <div className="fixed inset-0 z-50">
      {/* 背景遮罩 */}
      <button
        type="button"
        aria-label="关闭详情"
        onClick={onClose}
        className="absolute inset-0 bg-black/30"
      />

      {/* 抽屉面板 */}
      <div className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col border-l bg-background shadow-xl">
        {/* 头部 */}
        <div className="flex items-start justify-between gap-3 border-b p-4">
          <div className="min-w-0 flex-1">
            <p className="text-base font-medium leading-snug">{dir.name}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {dir.type && <Tag>{relationLabel(dir.type)}</Tag>}
              {dir.motivation && <Tag>{cleanLabel(dir.motivation)}</Tag>}
              {dir.evidence_level && <Tag>{evidenceLevelLabel(dir.evidence_level)}</Tag>}
              {dir.stickiness && <Tag>粘性{cleanLabel(dir.stickiness)}</Tag>}
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <span
              className={`flex h-10 w-14 items-center justify-center rounded-lg text-lg font-bold ${tone.bg} ${tone.text}`}
            >
              {dir.score ?? "-"}
            </span>
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭"
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* 内容区 */}
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
          {motivation && (
            <DrawerBlock icon={<Search className="h-4 w-4" />} title="动机证据">
              <p className="text-sm leading-relaxed text-muted-foreground">{motivation}</p>
            </DrawerBlock>
          )}

          {/* 成本三卡 */}
          <div className="grid grid-cols-3 gap-2">
            <StatCard label="1688成本" value={cleanLabel(dir.cost) || "-"} />
            <StatCard label="定价策略" value={formatStrategy(dir.strategy) || "-"} small />
            <StatCard label="证据级" value={evidenceLevelLabel(dir.evidence_level) || "-"} />
          </div>

          {deepArgs?.content && (
            <DrawerBlock icon={<Scale className="h-4 w-4" />} title="深度论证">
              <FieldGrid content={deepArgs.content} dense />
            </DrawerBlock>
          )}

          {delivery?.content && (
            <DrawerBlock icon={<PackageCheck className="h-4 w-4" />} title="交付清单">
              <FieldGrid content={delivery.content} dense />
            </DrawerBlock>
          )}

          {!dirSection && (
            <p className="text-xs text-muted-foreground">
              未找到该方向的详细分析原文（可能来自旧版本任务）。
            </p>
          )}
        </div>

        {/* 底部操作 */}
        <div className="flex gap-2 border-t p-3">
          <button
            type="button"
            onClick={copyInfo}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm hover:bg-muted"
          >
            <Copy className="h-3.5 w-3.5" />
            复制方向信息
          </button>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
      {children}
    </span>
  );
}

function DrawerBlock({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-sm font-medium">
        <span className="text-muted-foreground">{icon}</span>
        {title}
      </p>
      {children}
    </div>
  );
}

function StatCard({
  label,
  value,
  small = false,
}: {
  label: string;
  value: string;
  small?: boolean;
}) {
  return (
    <div className="rounded-lg bg-muted/50 px-2.5 py-2">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p
        className={`mt-0.5 break-words font-medium ${small ? "text-xs leading-snug" : "text-sm"}`}
      >
        {value}
      </p>
    </div>
  );
}
