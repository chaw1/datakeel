import { useI18n } from "../../i18n/useI18n";

import { TrainingSamples } from "./TrainingSamples";

import type { TrainingReport } from "../../api/llmData";
import type { MessageKey } from "../../i18n/en";

const languageNames: Partial<Record<string, MessageKey>> = {
  zh: "llmDataLanguageZh",
  en: "llmDataLanguageEn",
  mixed: "llmDataLanguageMixed",
  unknown: "llmDataLanguageUnknown",
};

export function TrainingReportView({ report }: { report: TrainingReport }) {
  const { t } = useI18n();
  return (
    <div className="llm-data-report">
      <p className="muted">
        {t("llmDataReportVersion", { version: report.rule_version })}
      </p>
      <dl className="llm-data-metrics">
        {(
          [
            ["llmDataRecords", report.records],
            ["llmDataValid", report.valid_records],
            ["llmDataKeep", report.kept],
            ["llmDataDrop", report.dropped],
            ["llmDataRedact", report.redacted],
          ] as const
        ).map(([label, count]) => (
          <div key={label}>
            <dt>{t(label)}</dt>
            <dd>{count.toLocaleString()}</dd>
          </div>
        ))}
      </dl>
      <div className="llm-data-summary-grid">
        <section aria-label={t("llmDataIssues")}>
          <h3>{t("llmDataIssues")}</h3>
          {!Object.keys(report.issue_counts ?? {}).length && (
            <p>{t("llmDataNoIssues")}</p>
          )}
          <dl className="llm-data-counts">
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
        <section aria-label={t("llmDataLanguages")}>
          <h3>{t("llmDataLanguages")}</h3>
          <dl className="llm-data-counts">
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
              <h4>{t("llmDataPreferences")}</h4>
              <p>
                {t("llmDataPreferenceRatio", {
                  count: report.preference_records,
                  ratio: (report.chosen_longer_ratio * 100).toFixed(1),
                })}
              </p>
            </>
          )}
        </section>
      </div>
      <details>
        <summary>{t("llmDataFiles")}</summary>
        <ul>
          {report.files.map((file) => (
            <li key={file.file_id}>
              <strong>{file.filename}</strong> ·{" "}
              {t("llmDataFileRecords", {
                valid: file.valid_records,
                total: file.records,
              })}
            </li>
          ))}
        </ul>
      </details>
      <TrainingSamples samples={report.samples} />
      <section aria-label={t("llmDataClusters")}>
        <h3>{t("llmDataClusters")}</h3>
        {!report.duplicate_clusters.length && <p>{t("llmDataNoClusters")}</p>}
        {report.duplicate_clusters.map((cluster, index) => (
          <details key={cluster.join(":")}>
            <summary>
              {t("llmDataCluster", {
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
      <section aria-label={t("llmDataContamination")}>
        <h3>{t("llmDataContamination")}</h3>
        {!report.contamination_hits.length && (
          <p>{t("llmDataNoContamination")}</p>
        )}
        <ul className="llm-data-findings">
          {report.contamination_hits.map((hit, index) => (
            <li key={`${hit.related_id ?? hit.code}:${String(index)}`}>
              <span>{hit.message}</span>
              {hit.related_id && (
                <code>
                  {t("llmDataEvaluationItem", { id: hit.related_id })}
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
