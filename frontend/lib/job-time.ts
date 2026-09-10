const TIME_ZONE = "Asia/Shanghai";

function validDate(value: string | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateParts(value: string | Date): Record<string, string> | null {
  const date = validDate(value);
  if (!date) return null;
  const formatted = new Intl.DateTimeFormat("zh-CN", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  return Object.fromEntries(formatted.map((part) => [part.type, part.value]));
}

export function formatBeijingTime(value: string | Date): string {
  const parts = dateParts(value);
  return parts ? parts.hour + ":" + parts.minute : "时间不可用";
}

export function beijingDateKey(value: string | Date): string {
  const parts = dateParts(value);
  return parts
    ? parts.year + "-" + parts.month + "-" + parts.day
    : "";
}

export function formatDuration(start: string | Date, end: string | Date): string {
  const startDate = validDate(start);
  const endDate = validDate(end);
  if (!startDate || !endDate) return "时间不可用";
  const seconds = Math.floor((endDate.getTime() - startDate.getTime()) / 1000);
  if (seconds < 0) return "时间不可用";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours > 0
    ? hours + "小时" + minutes + "分" + remainder + "秒"
    : minutes + "分" + remainder + "秒";
}
