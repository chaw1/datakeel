import { useI18n } from "../../../i18n/useI18n";

import { AccuracyHeadline } from "./AccuracyHeadline";
import { ThresholdBasis } from "./ThresholdBasis";
import "./ai.css";

import type { ProjectWorkbench } from "../../../api/production";

/** Model drafts on this project: confidence, accuracy against approved work, tiers and spend. */
export function PrelabelPanel({ data }: { data: ProjectWorkbench }) {
  const { t, locale } = useI18n();
  const count = new Intl.NumberFormat(locale);
  return (
    <section className="card wb-prelabels" aria-label={t("wbPrelabels")}>
      <h2>{t("wbPrelabels")}</h2>
      <dl className="wb-counts">
        {data.confidence.buckets.map((bucket) => (
          <div key={bucket.lower}>
            <dt>{`${String(bucket.lower)} – ${String(bucket.upper)}`}</dt>
            <dd>{bucket.count}</dd>
          </div>
        ))}
      </dl>
      <AccuracyHeadline accuracy={data.prelabel_accuracy} />
      <ThresholdBasis thresholds={data.confidence_thresholds} />
      <h3>{t("wbPrelabelSpend")}</h3>
      {data.prelabel_spend.length ? (
        <div className="table-wrap">
          <table aria-label={t("wbPrelabelSpend")}>
            <thead>
              <tr>
                <th>{t("wbSpendModel")}</th>
                <th>{t("wbSpendRuns")}</th>
                <th>{t("wbSpendImages")}</th>
                <th>{t("wbSpendInput")}</th>
                <th>{t("wbSpendOutput")}</th>
                <th>{t("wbSpendCost")}</th>
              </tr>
            </thead>
            <tbody>
              {data.prelabel_spend.map((spend) => (
                <tr key={spend.model_id}>
                  <td>{`${spend.model_name}@${spend.model_version}`}</td>
                  <td>{count.format(spend.runs)}</td>
                  <td>{count.format(spend.images)}</td>
                  <td>{count.format(spend.input_tokens)}</td>
                  <td>{count.format(spend.output_tokens)}</td>
                  <td>{`${spend.cost.toFixed(4)} ${spend.currency}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">{t("wbNoPrelabelSpend")}</p>
      )}
    </section>
  );
}
