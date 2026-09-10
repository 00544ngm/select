export function splitDirectionName(name: string): { zh: string; en: string } {
  const match = name
    .trim()
    .match(/^(.*?)\s*[（(]([A-Za-z][^()（）]*)[)）]\s*$/);
  return match
    ? { zh: match[1].trim(), en: match[2].trim() }
    : { zh: name.trim(), en: "" };
}

export function directionQuery(direction: {
  name: string;
  keywords?: Record<string, string>;
}): string {
  return (
    direction.keywords?.amazon?.trim() ||
    direction.keywords?.en?.trim() ||
    splitDirectionName(direction.name).en
  );
}

export function normalizeRelationReasons(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (!value || typeof value !== "object") return [];
  return Object.values(value as Record<string, unknown>)
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

export function normalizeExtendedScenarios(value: unknown): Array<{
  name: string;
  assumption?: string;
  reason?: string;
}> {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item === "string") return [{ name: item }];
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const name = typeof record.name === "string" ? record.name : "";
    return name ? [{
      name,
      assumption: typeof record.assumption === "string" ? record.assumption : undefined,
      reason: typeof record.reason === "string" ? record.reason : undefined,
    }] : [];
  });
}

export function highestDirection<T extends { score?: number; final_score?: number; stickiness_score?: number; rejected?: boolean; name?: string }>(
  directions: T[]
): T | undefined {
  return rankDirections(directions)[0];
}

export function directionFinalScore(direction: {
  score?: number;
  final_score?: number;
  stickiness_score?: number;
}): number {
  return direction.stickiness_score ?? direction.final_score ?? direction.score ?? 0;
}

export function rankDirections<T extends {
  score?: number;
  final_score?: number;
  stickiness_score?: number;
  rejected?: boolean;
  name?: string;
}>(directions: T[]): T[] {
  return [...directions].sort((a, b) => {
    const rejectedOrder = Number(Boolean(a.rejected)) - Number(Boolean(b.rejected));
    if (rejectedOrder) return rejectedOrder;
    const scoreOrder = directionFinalScore(b) - directionFinalScore(a);
    if (scoreOrder) return scoreOrder;
    return (a.name ?? "").localeCompare(b.name ?? "");
  });
}

export function recommendationLabel(level?: string): string {
  switch (level) {
    case "focus": return "重点开发";
    case "test_pool": return "测试池";
    case "observe": return "观察验证";
    default: return "不推荐";
  }
}
