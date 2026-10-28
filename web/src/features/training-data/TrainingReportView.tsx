import { useI18n } from "../../i18n/useI18n";

import { TrainingSamples } from "./TrainingSamples";

import type { TrainingReport } from "../../api/trainingData";
import type { MessageKey } from "../../i18n/en";

const languageNames: Partial<Record<string, MessageKey>> = {
  zh: "trainingLanguageZh",
  en: "trainingLanguageEn",
  mixed: "trainingLanguageMixed",
  unknown: "trainingLanguageUnknown",
};

export function TrainingReportView({ report }: { report: TrainingReport }) {
  const { t } = useI18n();
  return (
    <div className="training-report">
      <p className="muted">
        {t("trainingReportVersion", { version: report.rule_version })}
      </p>
      <dl className="training-metrics">
        {(
          [
            ["trainingRecords", report.records],
            ["trainingValid", report.valid_records],
            ["trainingKeep", report.kept],
            ["trainingDrop", report.dropped],
            ["trainingRedact", report.redacted],
          ] as const
        ).map(([label, count]) => (
          <div key={label}>
            <dt>{t(label)}</dt>
            <dd>{count.toLocaleString()}</dd>
          </div>
        ))}
      </dl>
      <div className="training-summary-grid">
        <section aria-label={t("trainingIssues")}>
          <h3>{t("trainingIssues")}</h3>
          {!Object.keys(report.issue_counts ?? {}).length && (
            <p>{t("trainingNoIssues")}</p>
          )}
          <dl className="training-counts">
            {Object.entries(report.issue_counts ?? {}).map(([code, count]) => (
              <div key={code}>
                <dt>
                  <code>{code}</code>
                </dt>
                <dd>{count.toLocaleString()}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section aria-label={t("trainingLanguages")}>
          <h3>{t("trainingLanguages")}</h3>
          <dl className="training-counts">
            {Object.entries(report.languages ?? {}).map(([language, count]) => (
              <div key={language}>
                <dt>
                  {languageNames[language]
                    ? t(languageNames[language])
                    : language}
                </dt>
                <dd>
                  {count.toLocaleString()} ·{" "}
                  {((count / Math.max(report.records, 1)) * 100).toFixed(1)}%
                </dd>
              </div>
            ))}
          </dl>
          {report.preference_records > 0 && (
            <>
              <h4>{t("trainingPreferences")}</h4>
              <p>
                {t("trainingPreferenceRatio", {
                  count: report.preference_records,
                  ratio: (report.chosen_longer_ratio * 100).toFixed(1),
                })}
              </p>
            </>
          )}
        </section>
      </div>
      <details>
        <summary>{t("trainingFiles")}</summary>
        <ul>
          {report.files.map((file) => (
            <li key={file.file_id}>
              <strong>{file.filename}</strong> ·{" "}
              {t("trainingFileRecords", {
                valid: file.valid_records,
                total: file.records,
              })}
            </li>
          ))}
        </ul>
      </details>
      <TrainingSamples samples={report.samples} />
      <section aria-label={t("trainingClusters")}>
        <h3>{t("trainingClusters")}</h3>
        {!report.duplicate_clusters.length && <p>{t("trainingNoClusters")}</p>}
        {report.duplicate_clusters.map((cluster, index) => (
          <details key={cluster.join(":")}>
            <summary>
              {t("trainingCluster", {
                number: index + 1,
                count: cluster.length,
              })}
            </summary>
            <ul>
              {cluster.map((id) => (
                <li key={id}>
                  <code>{id}</code>
                </li>
              ))}
            </ul>
          </details>
        ))}
      </section>
      <section aria-label={t("trainingContamination")}>
        <h3>{t("trainingContamination")}</h3>
        {!report.contamination_hits.length && (
          <p>{t("trainingNoContamination")}</p>
        )}
        <ul className="training-findings">
          {report.contamination_hits.map((hit, index) => (
            <li key={`${hit.related_id ?? hit.code}:${String(index)}`}>
              <span>{hit.message}</span>
              {hit.related_id && (
                <code>
                  {t("trainingEvaluationItem", { id: hit.related_id })}
                </code>
              )}
              {hit.evidence && <mark>{hit.evidence}</mark>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
