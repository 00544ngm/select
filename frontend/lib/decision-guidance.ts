import type { StructuredDirection } from "@/lib/api/types";

export type EmployeeDecisionStatus =
  | "pass"
  | "hold"
  | "reject"
  | "historical_incomplete";

export interface DecisionGuidance {
  status: EmployeeDecisionStatus;
  title: string;
  reason: string;
  nextStep: string;
  meaning: string;
}

const rejectReasonFields = {
  incompatible: ["compatibility_status", "incompatibility_reason"],
  duplicate_function: ["duplication_status", "duplicate_function_reason"],
  safety_blocked: ["safety_status", "safety_risk"],
} as const;

function firstMissingEvidence(direction: StructuredDirection): string {
  return direction.missing_evidence?.find((item) => item.trim()) ?? "";
}

function hasCompleteRejectEvidence(direction: StructuredDirection): boolean {
  const codes = direction.rejection_codes ?? [];
  if (!codes.length || !direction.source_fact_ids?.length) return false;

  return codes.every((code) => {
    const fields = rejectReasonFields[code as keyof typeof rejectReasonFields];
    if (fields) {
      const [statusField, reasonField] = fields;
      return (
        direction[statusField] === "blocked" &&
        Boolean(direction[reasonField]?.trim())
      );
    }
    if (code === "food_blocked") {
      return (
        direction.product_type_status === "food" ||
        direction.product_type_status === "ingestible"
      );
    }
    if (code === "reverse_dependency") {
      return direction.purchase_direction === "reverse_dependency";
    }
    if (code === "no_valid_relation") {
      return (
        direction.primary_relation === "none" ||
        direction.primary_relation === "weak_context"
      );
    }
    return true;
  });
}

function confirmedRejectReason(direction: StructuredDirection): string {
  return (
    direction.incompatibility_reason?.trim() ||
    direction.duplicate_function_reason?.trim() ||
    direction.safety_risk?.trim() ||
    direction.rejection_reason?.trim() ||
    "已有事实确认当前候选存在阻断。"
  );
}

export function buildDecisionGuidance(
  direction: StructuredDirection
): DecisionGuidance {
  const missing = firstMissingEvidence(direction);

  if (
    direction.execution_status === "reject" &&
    !hasCompleteRejectEvidence(direction)
  ) {
    return {
      status: "historical_incomplete",
      title: "历史判定证据不完整",
      reason: "旧结果包含拒绝代码，但没有保存完整的阻断理由和事实来源。",
      nextStep: missing
        ? `建议按新规则重新分析，并核对：${missing}`
        : "建议按新规则重新分析。",
      meaning: "不能据此判断这个辅品永久不能做。",
    };
  }

  if (direction.execution_status === "reject") {
    return {
      status: "reject",
      title: "当前方案暂不进入测试",
      reason: confirmedRejectReason(direction),
      nextStep: "更换具体候选商品或解除上述阻断后重新分析。",
      meaning: "这是对当前候选方案的判断，不是否定整个辅品品类。",
    };
  }

  if (direction.execution_status === "hold") {
    return {
      status: "hold",
      title: "补充证据后复核",
      reason: missing || "当前兼容、安全或产品信息尚未核实完整。",
      nextStep: missing ? `请核对：${missing}` : "补齐缺失证据后重新评估。",
      meaning: "当前证据不足，不代表这个辅品不能做。",
    };
  }

  return {
    status: "pass",
    title: "可进入测试",
    reason: direction.direction_reason || "当前未发现确定阻断。",
    nextStep: "按最终测试等级执行，并继续核对具体商品规格。",
    meaning: "通过准入不等于保证销售结果，仍需用市场测试验证。",
  };
}
