import type { Locale } from "../../i18n/context";

export function money(value: string | number, locale: Locale): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 6,
    maximumFractionDigits: 8,
  }).format(Number(value));
}
export function cacheRate(input: number, cached: number): string {
  return `${(input > 0 ? (cached / input) * 100 : 0).toFixed(1)}%`;
}
