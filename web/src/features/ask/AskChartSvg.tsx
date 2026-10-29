import { useId } from "react";

import { useI18n } from "../../i18n/useI18n";

import {
  chartDomain,
  chartLabel,
  chartNumber,
  chartPoints,
  chartTickIndices,
} from "./chartData";

import type { ChartSpec, ChartType, QueryResult } from "./chartData";

export function AskChartSvg({
  result,
  chart,
  type,
}: {
  result: QueryResult;
  chart: ChartSpec;
  type: ChartType;
}) {
  const { locale, t } = useI18n();
  const titleId = useId();
  const descriptionId = useId();
  const points = chartPoints(result, chart);
  const categories = [...new Set(points.map((point) => point.category))];
  const series = [...new Set(points.map((point) => point.series))];
  const horizontal = type === "horizontal_bar";
  const stacked = type === "stacked_bar";
  const grouped = type === "grouped_bar";
  const { minimum, maximum } = chartDomain(points, stacked);
  const height = horizontal ? Math.max(240, categories.length * 40 + 96) : 360;
  const left = horizontal ? 164 : 80;
  const bottom = horizontal ? height - 48 : 280;
  const width = 720 - left;
  const plotHeight = bottom - 24;
  const xValue = (value: number) =>
    left + ((value - minimum) / (maximum - minimum)) * width;
  const yValue = (value: number) =>
    bottom - ((value - minimum) / (maximum - minimum)) * plotHeight;
  const step = horizontal
    ? plotHeight / Math.max(1, categories.length)
    : width / Math.max(1, categories.length);
  const xCategory = (category: string) =>
    left + step * (categories.indexOf(category) + 0.5);
  const number = (value: number) => chartNumber(value, chart, locale);
  const ticks = chartTickIndices(categories.length);
  return (
    <figure className="ask-chart-figure">
      <svg
        viewBox={`0 0 800 ${String(height)}`}
        role="img"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <title id={titleId}>{chart.title}</title>
        <desc
          id={descriptionId}
        >{`${chart.description}. ${t("askChartDescription")}${chart.unit ? ` ${chart.unit}` : ""}`}</desc>
        <path
          d={`M ${String(left)} 24 V ${String(bottom)} H 720`}
          className="ask-chart-axis"
        />
        {horizontal ? (
          <>
            <text x={left} y={height - 16}>
              {number(minimum)}
            </text>
            <text x="720" y={height - 16} textAnchor="end">
              {number(maximum)}
            </text>
            <path
              d={`M ${String(xValue(0))} 24 V ${String(bottom)}`}
              className="ask-chart-axis"
            />
          </>
        ) : (
          <>
            <text x={left - 8} y="24" textAnchor="end">
              {number(maximum)}
            </text>
            <text x={left - 8} y={bottom} textAnchor="end">
              {number(minimum)}
            </text>
            <path
              d={`M ${String(left)} ${String(yValue(0))} H 720`}
              className="ask-chart-axis"
            />
          </>
        )}
        {type === "line" && (
          <polyline
            points={points
              .map(
                (point) =>
                  `${String(xCategory(point.category))},${String(yValue(point.value))}`,
              )
              .join(" ")}
            className="ask-chart-line"
          />
        )}
        {points.map((point) => {
          const categoryIndex = categories.indexOf(point.category);
          const seriesIndex = series.indexOf(point.series);
          const total = points.reduce((sum, item) => sum + item.value, 0);
          const share =
            chart.show_percent && total !== 0
              ? ` · ${new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 2 }).format(point.value / total)}`
              : "";
          const label = `${point.category}${point.series ? ` · ${point.series}` : ""}: ${number(point.value)}${chart.unit ? ` ${chart.unit}` : ""}${share}`;
          const previous = stacked
            ? points
                .filter(
                  (item) =>
                    item.category === point.category &&
                    item.rowIndex < point.rowIndex &&
                    item.value >= 0 === point.value >= 0,
                )
                .reduce((sum, item) => sum + item.value, 0)
            : 0;
          const barWidth =
            (step * 0.72) / (grouped ? Math.max(1, series.length) : 1);
          const baseline = yValue(previous);
          const end = yValue(previous + point.value);
          return (
            <g
              key={point.rowIndex}
              className={`ask-chart-series-${String(seriesIndex % 5)}`}
              data-row={point.rowIndex}
              data-value={point.value}
            >
              <title>{label}</title>
              {type === "line" ? (
                <circle
                  cx={xCategory(point.category)}
                  cy={end}
                  r="5"
                  className="ask-chart-mark"
                />
              ) : horizontal ? (
                <rect
                  x={Math.min(xValue(0), xValue(point.value))}
                  y={24 + step * categoryIndex + step * 0.16}
                  width={Math.abs(xValue(point.value) - xValue(0))}
                  height={step * 0.68}
                  className="ask-chart-mark"
                />
              ) : (
                <rect
                  x={
                    xCategory(point.category) -
                    step * 0.36 +
                    (grouped ? seriesIndex * barWidth : 0)
                  }
                  y={Math.min(baseline, end)}
                  width={barWidth}
                  height={Math.abs(end - baseline)}
                  className="ask-chart-mark"
                />
              )}
              {chart.show_percent && !grouped && !stacked && (
                <text
                  x={
                    horizontal
                      ? xValue(point.value) + 6
                      : xCategory(point.category)
                  }
                  y={horizontal ? 24 + step * (categoryIndex + 0.6) : end - 8}
                  textAnchor={horizontal ? "start" : "middle"}
                >
                  {share.replace(" · ", "")}
                </text>
              )}
            </g>
          );
        })}
        {categories.map(
          (category, index) =>
            (horizontal || ticks.has(index)) && (
              <text
                key={category}
                data-category-index={index}
                x={horizontal ? left - 12 : xCategory(category)}
                y={horizontal ? 24 + step * (index + 0.6) : bottom + 28}
                textAnchor={horizontal ? "end" : "middle"}
              >
                <title>{category}</title>
                {chartLabel(
                  category,
                  horizontal
                    ? left - 24
                    : width / Math.min(6, categories.length) - 12,
                )}
              </text>
            ),
        )}
      </svg>
      <figcaption>
        {chart.unit && <span>{chart.unit}</span>}
        {chart.series &&
          series.map((name, index) => (
            <span
              className={`ask-chart-legend ask-chart-series-${String(index % 5)}`}
              key={name}
            >
              {name}
            </span>
          ))}
      </figcaption>
    </figure>
  );
}
