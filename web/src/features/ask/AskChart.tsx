import { useId, useState } from "react";

import { FootnoteReference } from "../../components/FootnoteReference";
import { useI18n } from "../../i18n/useI18n";

import { AskChartSvg } from "./AskChartSvg";
import { chartNumber } from "./chartData";

import "./charts.css";

import type { ChartSpec, ChartType } from "./chartData";
import type { AskAnswer } from "../../api/ask";
import type { FootnoteItem } from "../../components/Footnotes";

const chartLabels = {
  scalar: "askChartScalar",
  line: "askChartLine",
  bar: "askChartBar",
  horizontal_bar: "askChartHorizontal",
  grouped_bar: "askChartGrouped",
  stacked_bar: "askChartStacked",
  table: "askChartTable",
} as const;

export function AskChart({
  answer,
  chart,
  footnotes,
}: {
  answer: AskAnswer;
  chart: ChartSpec;
  footnotes: FootnoteItem[];
}) {
  const { t, locale } = useI18n();
  const selectId = useId();
  const descriptionId = useId();
  const [type, setType] = useState<ChartType>(chart.type);
  const views: ChartType[] =
    chart.type === "table" ? ["table"] : [chart.type, "table"];
  const result = answer.result;
  if (!result?.rows.length) return <p>{t("askNoRows")}</p>;
  const format = (value: (typeof result.rows)[number][number]) => {
    if (value === null) return t("askNull");
    if (typeof value === "boolean") return t(value ? "askTrue" : "askFalse");
    return typeof value === "number"
      ? chartNumber(value, chart, locale)
      : value;
  };
  const comparison = answer.comparison?.changes[0];
  const missingBaseline = answer.comparison?.changes.some(
    (change) => change.previous_value == null,
  );
  const zeroBaseline = answer.comparison?.changes.some(
    (change) => change.previous_value === 0,
  );
  return (
    <section
      className="ask-chart"
      aria-label={chart.title}
      aria-describedby={descriptionId}
    >
      <p id={descriptionId} className="sr-only">
        {chart.description}. {t("askChartDescription")}
      </p>
      <div
        className="ask-chart-controls"
        role="group"
        aria-labelledby={selectId}
      >
        <span id={selectId}>{t("askChartView")}</span>
        {views.map((option) => (
          <button
            className="button"
            type="button"
            aria-pressed={type === option}
            onClick={() => {
              setType(option);
            }}
            key={option}
          >
            {t(chartLabels[option])}
          </button>
        ))}
      </div>
      {type === "table" ? (
        <div className="ask-table-scroll">
          <table>
            <caption>{t("askResults")}</caption>
            <thead>
              <tr>
                {result.columns.map((column) => (
                  <th key={column} scope="col">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, index) => (
                <tr key={index}>
                  {row.map((value, column) => (
                    <td key={column}>
                      {typeof value === "number" &&
                      !chart.y.includes(result.columns[column])
                        ? String(value)
                        : format(value)}
                      {typeof value === "number" &&
                      chart.y.includes(result.columns[column]) &&
                      chart.unit
                        ? ` ${chart.unit}`
                        : ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : type === "scalar" ? (
        <div className="ask-number-line">
          <output
            className="ask-scalar answer-number"
            aria-label={t("askResult")}
          >
            {format(result.rows[0]?.[0] ?? null)}
          </output>
          {chart.unit && <span>{chart.unit}</span>}
          <span className="ask-answer-references">
            {footnotes.map((item, index) => (
              <FootnoteReference item={item} index={index} key={item.id} />
            ))}
          </span>
        </div>
      ) : (
        <AskChartSvg result={result} chart={chart} type={type} />
      )}
      {type === "scalar" && comparison && (
        <p className="ask-comparison">
          {t("askChartChange")}:{" "}
          {comparison.delta == null
            ? t("askComparisonMissing")
            : `${chartNumber(comparison.delta, chart, locale)}${chart.unit ? ` ${chart.unit}` : ""}`}
          {comparison.percent_change != null &&
            ` (${new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 2 }).format(comparison.percent_change / 100)})`}
        </p>
      )}
      {type !== "scalar" && missingBaseline && (
        <p className="ask-comparison">{t("askComparisonMissingGroups")}</p>
      )}
      {zeroBaseline && (
        <p className="ask-comparison">{t("askComparisonZeroBaseline")}</p>
      )}
      {type !== "scalar" && (
        <span className="ask-answer-references">
          {footnotes.map((item, index) => (
            <FootnoteReference item={item} index={index} key={item.id} />
          ))}
        </span>
      )}
    </section>
  );
}
