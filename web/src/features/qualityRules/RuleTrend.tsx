import { useId } from "react";

import { useI18n } from "../../i18n/useI18n";
import { date, timestamp } from "../../lib/format";

import { resultStatuses } from "./ruleLabels";

import type { DqResult } from "../../api/qualityRules";

export function RuleTrend({ results }: { results: DqResult[] }) {
  const { t, locale } = useI18n();
  const titleId = useId();
  const descriptionId = useId();
  const points = results
    .filter((result) => result.actual_value != null)
    .sort((a, b) => timestamp(a.started_at) - timestamp(b.started_at));
  if (!points.length) return <p className="muted">{t("dqNoTrend")}</p>;
  const values = points.flatMap((point) => [
    point.actual_value ?? 0,
    point.threshold,
  ]);
  const minimum = Math.min(0, ...values);
  const maximum = Math.max(1, ...values);
  const x = (index: number) =>
    48 + (index * 576) / Math.max(1, points.length - 1);
  const y = (value: number) =>
    150 - ((value - minimum) / (maximum - minimum)) * 120;
  return (
    <figure className="dq-trend">
      <svg
        viewBox="0 0 672 196"
        role="img"
        aria-labelledby={`${titleId} ${descriptionId}`}
      >
        <title id={titleId}>{t("dqTrend")}</title>
        <desc id={descriptionId}>{t("dqTrendHelp")}</desc>
        <path d="M 48 24 V 150 H 624" className="dq-chart-axis" />
        <text x="4" y="32">
          {maximum.toLocaleString(locale)}
        </text>
        <text x="4" y="150">
          {minimum.toLocaleString(locale)}
        </text>
        <polyline
          points={points
            .map(
              (point, index) =>
                `${String(x(index))},${String(y(point.threshold))}`,
            )
            .join(" ")}
          className="dq-chart-threshold"
        />
        <polyline
          points={points
            .map(
              (point, index) =>
                `${String(x(index))},${String(y(point.actual_value ?? 0))}`,
            )
            .join(" ")}
          className="dq-chart-line"
        />
        {points.map((point, index) => (
          <circle
            key={point.id}
            cx={x(index)}
            cy={y(point.actual_value ?? 0)}
            r="4"
            className={`dq-point dq-${point.status}`}
          >
            <title>{`${date(point.started_at, locale)} · ${t(resultStatuses[point.status])} · ${String(point.actual_value)}`}</title>
          </circle>
        ))}
        <text x="48" y="178">
          {date(points[0].started_at, locale)}
        </text>
        {points.length > 1 && (
          <text x="624" y="178" textAnchor="end">
            {date(points[points.length - 1].started_at, locale)}
          </text>
        )}
      </svg>
      <figcaption>
        <span className="dq-legend-actual">{t("dqActual")}</span>
        <span className="dq-legend-threshold">{t("dqThreshold")}</span>
      </figcaption>
    </figure>
  );
}
