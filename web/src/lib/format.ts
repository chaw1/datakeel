import type { Task } from "../api/types";
import type { Locale } from "../i18n/context";
export function display(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "string") return value;
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  )
    return String(value);
  return JSON.stringify(value);
}

export function timestamp(value?: string | number): number {
  if (value === undefined) return 0;
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(numeric))
    return Math.abs(numeric) < 1e12 ? numeric * 1000 : numeric;
  return new Date(value).getTime();
}

export function date(
  value?: string | number,
  locale: Locale = "en",
  timeZone?: string,
): string {
  if (value === undefined) return "—";
  const parsed = new Date(timestamp(value));
  if (Number.isNaN(parsed.getTime())) return String(value);
  const parts = new Intl.DateTimeFormat(locale, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone,
  }).formatToParts(parsed);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "";
  return `${part("month")}-${part("day")} ${part("hour")}:${part("minute")}`;
}

export function bytes(value?: number): string {
  if (value === undefined) return "—";
  if (value < 1024) return `${String(value)} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export function taskProgress(task: Task): number {
  const value =
    task.state.toUpperCase() === "COMPLETED"
      ? 100
      : task.total_shards
        ? ((task.completed_shards || 0) / task.total_shards) * 100
        : task.progress || 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}
