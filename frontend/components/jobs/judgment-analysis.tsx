"use client";

import { useEffect, useMemo, useState } from "react";
import { X, ChevronRight, ShieldCheck, ShieldX } from "lucide-react";
import FieldGrid from "@/components/jobs/field-grid";
import ProductMedia from "@/components/jobs/product-media";
import VetoReviewPanel from "@/components/jobs/veto-review-panel";
import type {
  ComplementEvidencePayload,
  ComplementEvidenceRecord,
  JudgmentBProductMetadata,
} from "@/lib/api/types";
import { resolveJudgmentProducts } from "@/lib/judgment-product-metadata";
import {
  cleanLabel,
  extractBProducts,
  scoreTone,
  type PerBProduct,
} from "@/lib/result-format";

interface Section {
  title: string;
  content?: string;
  children?: Section[];
}

interface JudgmentAnalysisProps {
  sections?: Section[];
  grade?: string;
  complementEvidence?: ComplementEvidencePayload;
  bProducts?: JudgmentBProductMetadata[];
  bUrls?: string[];
}

/**
 * 审判结果（模式B）的方案分析视图：
 * 每个 B 品一张结论卡（C分 / B分 / 否决状态），点卡开右侧抽屉看 8 项审查详情。
 * 数据由前端从 sections 文本解析；旧任务解析不出时显示提示，完整内容仍在「结果详情」。
 */
export default function JudgmentAnalysis({
  sections,
  grade,
  complementEvidence,
  bProducts,
  bUrls,
}: JudgmentAnalysisProps) {
  const parsedProducts = useMemo(() => extractBProducts(sections), [sections]);
  const products = useMemo(
    () => resolveJudgmentProducts(parsedProducts, bProducts, bUrls),
    [parsedProducts, bProducts, bUrls],
  );
  const [detail, setDetail] = useState<PerBProduct | null>(null);

  if (products.length === 0) {
    return (
      <p className="rounded-xl border p-4 text-sm text-muted-foreground">
        本任务未能按 B 品拆分展示（可能是旧版本任务数据），完整审查内容请查看「结果详情」。
      </p>
    );
  }

  return (
    <div className="space-y-1.5">
      {products.map((p) => {
        const tone = scoreTone(p.cTotal);
        return (
          <div
            key={p.name}
            role="button"
            tabIndex={0}
            onClick={() => setDetail(p)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setDetail(p);
              }
            }}
            className="flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-colors hover:bg-muted/30"
          >
            <ProductMedia
              src={p.productImage}
              alt={p.name}
              emptyLabel={p.productUrl ? "暂无图片" : "历史无图"}
              className="w-12 rounded-lg"
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{p.name}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {p.productId ? `商品 ID：${p.productId}` : "商品 ID 未记录"}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {p.cTotal != null && <>C组合分 {p.cTotal}</>}
                {p.cTotal != null && p.bTotal != null && " · "}
                {p.bTotal != null && <>B执行分 {p.bTotal}</>}
                {p.vetoed && p.vetoReason && (
                  <span className="text-destructive"> · {p.vetoReason}</span>
                )}
              </p>
            </div>

            {p.vetoed === true ? (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-red-50 px-2 py-1 text-xs font-medium text-red-700">
                <ShieldX className="h-3.5 w-3.5" />
                否决
              </span>
            ) : p.vetoed === false ? (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
                <ShieldCheck className="h-3.5 w-3.5" />
                通过
              </span>
            ) : null}

            {p.cTotal != null && (
              <span
                className={`flex h-8 w-11 shrink-0 items-center justify-center rounded-lg text-sm font-bold ${tone.bg} ${tone.text}`}
              >
                {p.cTotal}
              </span>
            )}
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          </div>
        );
      })}

      {grade && (
        <p className="pt-2 text-center text-xs text-muted-foreground">
          最终评级：{cleanLabel(grade)}
        </p>
      )}

      {detail && (
        <BProductDrawer
          product={detail}
          evidence={findEvidence(complementEvidence, detail.name)}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}

function BProductDrawer({
  product,
  evidence,
  onClose,
}: {
  product: PerBProduct;
  evidence?: ComplementEvidenceRecord;
  onClose: () => void;
}) {
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

  const tone = scoreTone(product.cTotal);

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="关闭详情"
        onClick={onClose}
        className="absolute inset-0 bg-black/30"
      />
      <div className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col border-l bg-background shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b p-4">
          <ProductMedia
            src={product.productImage}
            alt={product.name}
            emptyLabel={product.productUrl ? "暂无图片" : "历史无图"}
            className="w-20 rounded-lg"
          />
          <div className="min-w-0 flex-1">
            <p className="text-base font-medium leading-snug">{product.name}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {product.productId ? `商品 ID：${product.productId}` : "商品 ID 未记录"}
            </p>
            {product.productUrl && (
              <a
                href={product.productUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex text-xs font-medium text-primary hover:underline"
              >
                打开商品
              </a>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
              {product.vetoed === true ? (
                <span className="rounded bg-red-50 px-1.5 py-0.5 text-red-700">
                  触发否决{product.vetoReason ? `：${product.vetoReason}` : ""}
                </span>
              ) : product.vetoed === false ? (
                <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700">
                  否决审查通过
                </span>
              ) : null}
              {product.bTotal != null && (
                <span className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">
                  B跨境执行分 {product.bTotal}
                </span>
              )}
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            {product.cTotal != null && (
              <span
                className={`flex h-10 w-14 items-center justify-center rounded-lg text-lg font-bold ${tone.bg} ${tone.text}`}
              >
                {product.cTotal}
              </span>
            )}
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

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
          <VetoReviewPanel product={product} evidence={evidence} />

          {product.sections.filter((section) => !section.title.includes("否决")).map((sec, i) => {
            const minDepth = Math.min(...sec.fields.map((f) => f.depth));
            const normalized = sec.fields.map((f) => ({
              ...f,
              depth: f.depth - minDepth,
            }));
            return (
              <div key={i}>
                <p className="mb-2 text-sm font-medium">{sec.title}</p>
                <FieldGrid fields={normalized} dense />
              </div>
            );
          })}
        </div>

        <div className="flex border-t p-3">
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

function findEvidence(
  payload: ComplementEvidencePayload | undefined,
  productName: string
): ComplementEvidenceRecord | undefined {
  const records = payload?.per_b_product;
  if (!records) return undefined;
  if (records[productName]) return records[productName];

  const normalizedProductName = normalizeProductTitle(productName);
  const matches = Object.values(records).filter((record) => {
    const normalizedTitle = normalizeProductTitle(record.product_title);
    if (normalizedTitle === normalizedProductName) return true;
    if (Math.min(normalizedTitle.length, normalizedProductName.length) < 12) {
      return false;
    }
    return (
      normalizedTitle.startsWith(normalizedProductName + " ") ||
      normalizedProductName.startsWith(normalizedTitle + " ")
    );
  });

  return matches.length === 1 ? matches[0] : undefined;
}

function normalizeProductTitle(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/\s+/g, " ");
}
