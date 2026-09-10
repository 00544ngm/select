"use client";

import { cleanLabel } from "@/lib/result-format";
import ProductMedia from "@/components/jobs/product-media";

interface ResultSummaryProps {
  grade?: string;
  gradeReason?: string;
  score?: number;
  scoreReason?: string;
  productId?: string;
  productTitle?: string;
  productTitleZh?: string;
  productImages?: string[];
}

export default function ResultSummary({
  grade,
  gradeReason,
  score,
  scoreReason,
  productId,
  productTitle,
  productTitleZh,
  productImages,
}: ResultSummaryProps) {
  const cleanGrade = cleanLabel(grade);
  const s = score ?? null;

  return (
    <div className="rounded-xl border p-5">
      <div className="flex items-start justify-between gap-4">
        {productImages?.length ? (
          <ProductMedia
            src={productImages}
            alt={productTitle || productTitleZh || "主品图片"}
            emptyLabel="暂无主品图片"
            className="w-20"
          />
        ) : null}
        <div className="min-w-0 flex-1">
          {productId && <p className="text-xs text-muted-foreground"><span>商品 ID：</span><span>{productId}</span></p>}
          {productTitleZh && (
            <p className="mt-1 text-sm font-semibold leading-relaxed">{productTitleZh}</p>
          )}
          {productTitle && (
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground"><span>原始标题：</span><span>{productTitle}</span></p>
          )}
          {cleanGrade && (
            <span className="mt-2 inline-block rounded-md bg-sky-50 px-2.5 py-1 text-xs font-medium text-sky-800">
              {cleanGrade}
            </span>
          )}
          {gradeReason && (
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
              {cleanLabel(gradeReason)}
            </p>
          )}
        </div>

        {s != null && <ScoreRing score={s} />}
      </div>

      {scoreReason && (
        <p className="mt-3 border-t pt-3 text-xs text-muted-foreground">
          {cleanLabel(scoreReason)}
        </p>
      )}
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  const stroke =
    pct >= 85 ? "#10b981" : pct >= 70 ? "#d97706" : "#9ca3af";

  return (
    <div className="shrink-0 text-center">
      <svg width="84" height="84" viewBox="0 0 84 84" role="img" aria-label={`综合评分 ${score}`}>
        <circle cx="42" cy="42" r={r} fill="none" strokeWidth="7" className="stroke-muted" />
        <circle
          cx="42"
          cy="42"
          r={r}
          fill="none"
          strokeWidth="7"
          stroke={stroke}
          strokeLinecap="round"
          strokeDasharray={`${(c * pct) / 100} ${c}`}
          transform="rotate(-90 42 42)"
        />
        <text
          x="42"
          y="41"
          textAnchor="middle"
          className="fill-foreground"
          fontSize="19"
          fontWeight="500"
        >
          {score}
        </text>
        <text
          x="42"
          y="56"
          textAnchor="middle"
          className="fill-muted-foreground"
          fontSize="9"
        >
          综合评分
        </text>
      </svg>
    </div>
  );
}
