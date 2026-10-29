import type { components } from "../../api/generated";

export type ChartSpec = components["schemas"]["ChartSpec"];
export type ChartType = ChartSpec["type"];
export type QueryResult = components["schemas"]["QueryResult"];
export type ChartPoint = {
  category: string;
  series: string;
  value: number;
  rowIndex: number;
};

export function chartPoints(
  result: QueryResult,
  chart: ChartSpec,
): ChartPoint[] {
  const x = result.columns.indexOf(chart.x ?? "");
  const y = result.columns.indexOf(chart.y[0] ?? "");
  const series = result.columns.indexOf(chart.series ?? "");
  return result.rows.flatMap((row, rowIndex) => {
    const value = row[y];
    return typeof value === "number" && Number.isFinite(value)
      ? [
          {
            category: String(row[x] ?? ""),
            series: String(row[series] ?? ""),
            value,
            rowIndex,
          },
        ]
      : [];
  });
}

export function chartNumber(value: number, chart: ChartSpec, locale: string) {
  return new Intl.NumberFormat(locale, {
    style: chart.number_format === "percent" ? "percent" : "decimal",
    maximumFractionDigits: chart.number_format === "integer" ? 0 : 8,
  }).format(value);
}

export function chartDomain(points: ChartPoint[], stacked: boolean) {
  const values = points.map((point) => point.value);
  if (stacked) {
    const categories = [...new Set(points.map((point) => point.category))];
    for (const category of categories) {
      const group = points.filter((point) => point.category === category);
      values.push(
        group.reduce((sum, point) => sum + Math.max(0, point.value), 0),
        group.reduce((sum, point) => sum + Math.min(0, point.value), 0),
      );
    }
  }
  return { minimum: Math.min(0, ...values), maximum: Math.max(1, ...values) };
}

export function chartLabel(label: string, width: number) {
  let used = 0;
  let visible = "";
  for (const character of label) {
    used += (character.codePointAt(0) ?? 0) > 255 ? 13 : 7;
    if (used > width - 14) return `${visible}…`;
    visible += character;
  }
  return visible;
}

export function chartTickIndices(count: number) {
  const ticks = Math.min(6, count);
  return new Set(
    Array.from({ length: ticks }, (_, index) =>
      Math.round((index * (count - 1)) / Math.max(1, ticks - 1)),
    ),
  );
}
