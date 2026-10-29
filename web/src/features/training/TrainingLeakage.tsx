import { useState } from "react";

import { trainingPath } from "../../api/training";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import type { LeakageReport, SplitSet } from "../../api/training";
import type { MessageKey } from "../../i18n/en";

const kinds: Record<LeakageReport["pairs"][number]["kind"], MessageKey> = {
  exact: "trainingExact",
  image: "trainingImage",
  text: "trainingText",
  group: "trainingGroupLeak",
};

export function TrainingLeakage({ split }: { split: SplitSet }) {
  const { t } = useI18n();
  const [checked, setChecked] = useState(false);
  const report = useResource<LeakageReport>(
    checked
      ? `${trainingPath(split.dataset_id, split.version_id)}/splits/${encodeURIComponent(split.id)}/leakage`
      : null,
  );
  function check() {
    if (checked) report.reload();
    setChecked(true);
  }
  return (
    <section className="training-leakage" aria-label={t("trainingLeakage")}>
      <div className="card-heading">
        <div>
          <h4>{t("trainingLeakage")}</h4>
          <p className="muted">{t("trainingLeakageHint")}</p>
          <p className="muted small">
            {t("trainingThresholds", {
              image: split.request.image_threshold,
              text: split.request.text_threshold,
            })}
          </p>
        </div>
        <button className="button" disabled={report.loading} onClick={check}>
          {t("trainingCheckLeakage")}
        </button>
      </div>
      <ResourceState {...report} onRetry={report.reload} />
      {report.value && (
        <p className="muted small">
          {t("trainingCheckedSignals", {
            signals: report.value.checked_signals
              .map((kind) => t(kinds[kind]))
              .join(", "),
          })}
        </p>
      )}
      {report.value && !report.value.pairs.length && (
        <p role="status">{t("trainingNoLeakage")}</p>
      )}
      {report.value && !!report.value.pairs.length && (
        <div className="table-scroll">
          <table>
            <caption>
              {t("trainingLeakageCount", { count: report.value.pairs.length })}
            </caption>
            <thead>
              <tr>
                <th scope="col">{t("trainingKind")}</th>
                <th scope="col">{t("trainingLeft")}</th>
                <th scope="col">{t("trainingRight")}</th>
                <th scope="col">{t("distance")}</th>
                <th scope="col">{t("trainingDetail")}</th>
              </tr>
            </thead>
            <tbody>
              {report.value.pairs.map((pair, index) => (
                <tr
                  key={`${pair.kind}:${pair.left_id}:${pair.right_id}:${String(index)}`}
                >
                  <th scope="row">{t(kinds[pair.kind])}</th>
                  <td>
                    <code>{pair.left_id}</code>
                    <br />
                    {pair.left_split}
                  </td>
                  <td>
                    <code>{pair.right_id}</code>
                    <br />
                    {pair.right_split}
                  </td>
                  <td>{pair.distance}</td>
                  <td>{pair.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
