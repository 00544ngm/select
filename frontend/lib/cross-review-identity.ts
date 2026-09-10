import type { CrossReviewState } from "@/lib/api/types";

export type CrossReviewReviewer = NonNullable<
  CrossReviewState["reviewers"]
>[number];

export interface CrossReviewDescription {
  title: string;
  reviewer?: CrossReviewReviewer;
  reviewed?: CrossReviewReviewer;
}

const CONCLUSION_TYPES = ["部分认可", "不认可", "无法判断", "认可"] as const;

function shortIdentity(identity: CrossReviewReviewer): string {
  const service = identity.display_name?.trim() || identity.provider.trim();
  return `${service}（${identity.model}）`;
}

export function formatFullIdentity(identity?: CrossReviewReviewer): string {
  if (!identity) return "历史任务未记录";
  const service = identity.display_name?.trim() || identity.provider.trim();
  const protocol =
    identity.api_protocol === "anthropic" ? "Anthropic 兼容" : "OpenAI 兼容";
  return `${service} · ${protocol} · ${identity.model}`;
}

export function describeCrossReviewEntry(
  key: string,
  reviewers: CrossReviewReviewer[],
): CrossReviewDescription {
  if (reviewers.length !== 0 && reviewers.length !== 2) {
    return { title: "交叉评审结果" };
  }

  const forward =
    key === "reviewer_a_reviews_reviewer_b" || key === "gpt_reviews_deepseek";
  const reverse = key === "reviewer_b_reviews_reviewer_a";
  if (!forward && !reverse) return { title: "交叉评审结果" };

  if (reviewers.length === 0) {
    return {
      title: forward
        ? "评审模型 A 评审 评审模型 B"
        : "评审模型 B 评审 评审模型 A",
    };
  }

  const reviewer = forward ? reviewers[0] : reviewers[1];
  const reviewed = forward ? reviewers[1] : reviewers[0];
  return {
    reviewer,
    reviewed,
    title: `${shortIdentity(reviewer)}评审 ${shortIdentity(reviewed)}`,
  };
}

export function extractCrossReviewSummary(raw?: string): {
  conclusionType: (typeof CONCLUSION_TYPES)[number];
  conclusion: string;
} {
  const typeMatch = raw?.match(
    /^结论类型[：:]\s*(认可|部分认可|不认可|无法判断)\s*$/m,
  );
  const conclusionMatch = raw?.match(/^一句话结论[：:]\s*(.+)\s*$/m);
  return {
    conclusionType:
      CONCLUSION_TYPES.find((value) => value === typeMatch?.[1]) ?? "无法判断",
    conclusion:
      conclusionMatch?.[1]?.trim() ||
      "旧任务未提供结构化结论，请查看评审原文。",
  };
}
