type LabelMap = Record<string, string>;

const relationLabels: LabelMap = {
  required_dependency: "必需依赖",
  spec_compatibility: "规格兼容",
  consumable_refill: "耗材补充",
  continuous_task: "连续任务",
  protection_maintenance: "保护维护",
  effect_enhancement: "效果增强",
  storage_transport: "收纳运输",
  style_occasion: "风格场合",
  weak_context: "弱关联",
  none: "无关联",
};

const purchaseDirectionLabels: LabelMap = {
  forward_dependency: "正向依赖",
  bidirectional: "双向购买",
  reverse_dependency: "反向依赖",
  none: "无明确方向",
};

const evidenceLabels: LabelMap = {
  E0: "未验证",
  E1: "候选发现",
  E2: "初步验证",
  E3: "较强验证",
  E4: "高可信验证",
};

const deepLabels: LabelMap = {
  user: "用户一致性",
  mental: "心智一致性",
  scenario: "场景一致性",
  lifecycle: "时间一致性",
  score: "评分",
  reason: "成立理由",
  purchase_chain: "购买链路",
  relation_reasons: "关系理由",
  extended_scenarios: "扩展场景",
  assumptions: "分析假设",
  consistency: "一致性评分",
  consumer_simulation: "消费者模拟",
  consumer_simulation_reason: "消费者模拟理由",
  delivery_checklist: "交付检查清单",
  before: "购买前",
  before_use: "使用前",
  primary_use: "使用主品",
  using_main: "使用主品",
  auxiliary_use: "使用辅品",
  using_candidate: "使用辅品",
  name: "场景名称",
  assumption: "场景假设",
  check_length: "长度检查",
  verify_hook_compatibility: "挂钩兼容性验证",
};

const decisionLabels: LabelMap = {
  not_recommended: "不建议",
  observe: "观察",
  needs_evidence: "需要证据",
  small_batch_test: "小批量测试",
  priority_test: "优先测试",
  focus_development: "重点开发",
};

const recommendationLabels: LabelMap = {
  focus: "重点开发",
  test_pool: "进入测试池",
  observe: "观察验证",
  not_recommended: "不建议",
};

const executionLabels: LabelMap = {
  pass: "可进入测试",
  hold: "待补证据后复核",
  reject: "确认不符合准入条件",
};

const rejectionCodeLabels: LabelMap = {
  incompatible: "已确认存在规格冲突",
  duplicate_function: "已确认核心功能重复",
  safety_blocked: "已确认存在具体安全风险",
  food_blocked: "属于禁止的食品或可摄入品",
  reverse_dependency: "购买方向与组合目标相反",
  no_valid_relation: "没有有效的共同购买任务",
};

function withOriginal(value: string, label: string | undefined): string {
  if (!label || label === value) return value;
  return `${label}（${value}）`;
}

export function relationLabel(value?: string | null): string {
  if (!value) return "关系未标注";
  return withOriginal(value, relationLabels[value]);
}

export function purchaseDirectionLabel(value?: string | null): string {
  if (!value) return "无明确方向";
  return withOriginal(value, purchaseDirectionLabels[value]);
}

export function evidenceLevelLabel(value?: string | null): string {
  if (!value) return "证据未知";
  return withOriginal(value, evidenceLabels[value]);
}

export function deepArgumentKeyLabel(value: string): string {
  return withOriginal(value, deepLabels[value]);
}

export function purchaseChainKeyLabel(value: string): string {
  return deepArgumentKeyLabel(value);
}

export function decisionActionLabel(value?: string | null): string {
  if (!value) return "-";
  return withOriginal(value, decisionLabels[value]);
}

export function executionStatusLabel(value?: string | null): string {
  if (!value) return "-";
  return executionLabels[value] ?? "待补证据后复核";
}

export function recommendationDisplayLabel(value?: string | null): string {
  if (!value) return "不建议";
  return withOriginal(value, recommendationLabels[value]);
}

export function rejectionCodeLabel(value: string): string {
  return withOriginal(value, rejectionCodeLabels[value]);
}

export function formatStrategy(value?: string | null): string {
  if (!value) return "-";
  const match = value.match(/^(bundled at|standalone at|discounted bundle)(\s+.*)?$/i);
  if (!match) return value;
  const prefix = match[1].toLowerCase();
  const labels: LabelMap = {
    "bundled at": "组合定价",
    "standalone at": "单独定价",
    "discounted bundle": "折扣组合",
  };
  return `${labels[prefix]}（${prefix}）${(match[2] ?? "").trim()}`.trim();
}

const phraseTranslations: Array<[string, string]> = [
  ["cat backpack carrier", "猫咪背包运输包"],
  ["pet carrier backpack", "宠物运输背包"],
  ["cat leash and harness set", "猫咪牵引绳和背带套装"],
  ["printer ink", "打印机墨盒"],
  ["ink cartridge", "墨盒"],
];

function translateKnownPhrases(value: string): string[] {
  const lower = value.toLowerCase();
  const matches = phraseTranslations
    .map(([phrase, translation]) => ({ phrase, translation, index: lower.indexOf(phrase) }))
    .filter((item) => item.index >= 0)
    .sort((a, b) => a.index - b.index || b.phrase.length - a.phrase.length);
  const covered: Array<{ start: number; end: number }> = [];
  return matches
    .filter((item) => {
      const overlaps = covered.some(({ start, end }) => item.index < end && item.index + item.phrase.length > start);
      if (!overlaps) covered.push({ start: item.index, end: item.index + item.phrase.length });
      return !overlaps;
    })
    .map((item) => item.translation);
}

export function formatKeywordDisplay(value?: Record<string, string> | string | null): string {
  if (!value) return "-";
  if (typeof value === "string") {
    const translated = translateKnownPhrases(value);
    return `英文搜索词（English）：${value}${translated.length ? `；中文释义：${translated.join("、")}` : ""}`;
  }
  const order = ["amazon", "walmart", "en", "keyword", "keywords"];
  const entries = Object.entries(value).sort(([a], [b]) => {
    const ai = order.indexOf(a);
    const bi = order.indexOf(b);
    return (ai < 0 ? order.length : ai) - (bi < 0 ? order.length : bi);
  }).filter(([, item]) => item?.trim());
  if (!entries.length) return "-";
  const english = entries.map(([key, item]) => `${key}：${item}`).join("；");
  const translated = entries.flatMap(([, item]) => translateKnownPhrases(item));
  return `英文搜索词（English）：${english}${translated.length ? `；中文释义：${[...new Set(translated)].join("、")}` : ""}`;
}
