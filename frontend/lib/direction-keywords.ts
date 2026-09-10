export type DirectionKeywords = {
  amazon: string;
  en: string;
};

export function normalizeDirectionKeywords(value: unknown): DirectionKeywords {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    return {
      amazon: typeof record.amazon === "string" ? record.amazon.trim() : "",
      en: typeof record.en === "string" ? record.en.trim() : "",
    };
  }
  if (typeof value !== "string") return { amazon: "", en: "" };
  const text = value.trim();
  const match = text.match(
    /^amazon\s*[:：]\s*(.*?)\s*[;；]\s*en\s*[:：]\s*(.+)$/i
  );
  return match
    ? { amazon: match[1].trim(), en: match[2].trim() }
    : { amazon: "", en: text };
}

export function amazonSearchUrl(query: string): string {
  return `https://www.amazon.com/s?k=${encodeURIComponent(query.trim())}`;
}
