import { useI18n } from "../../i18n/useI18n";

import { TrainingPreview } from "./TrainingPreview";

import type { TrainingRecord } from "../../api/llmData";

const decisions = {
  keep: "llmDataKeep",
  drop: "llmDataDrop",
  redact: "llmDataRedact",
} as const;

export function TrainingSamples({ samples }: { samples: TrainingRecord[] }) {
  const { t } = useI18n();
  return (
    <section aria-label={t("llmDataSamples")}>
      <h3>{t("llmDataSamples")}</h3>
      <p className="muted">{t("llmDataSamplesHint")}</p>
      {!samples.length && <p>{t("llmDataNoSamples")}</p>}
      <div className="llm-data-samples">
        {samples.map((record) => (
          <article
            className="llm-data-record"
            id={`llm-data-${record.id}`}
            key={record.id}
          >
            <h4>
              {t("llmDataRecordLocation", {
                file: record.file_id,
                line: record.line,
              })}
            </h4>
            <code className="llm-data-id">{record.id}</code>
            <p className="muted">
              {t("llmDataConfidence", {
                confidence: Math.round(record.language_confidence * 100),
                tokens: record.estimated_tokens,
              })}
            </p>
            <TrainingPreview record={record} />
            <p>
              <strong>
                {t("llmDataDecision")}: {t(decisions[record.decision])}
              </strong>
            </p>
            {!!record.reasons.length && (
              <p>
                {t("llmDataReasons")}: {record.reasons.join(" · ")}
              </p>
            )}
            <ul className="llm-data-findings">
              {record.issues.map((issue, index) => (
                <li key={`${issue.code}:${String(index)}`}>
                  <code>{issue.code}</code> · <span>{issue.message}</span>
                  <small>
                    {issue.field}
                    {issue.start !== null && issue.start !== undefined
                      ? ` [${String(issue.start)}, ${String(issue.end ?? issue.start)})`
                      : ""}
                  </small>
                  {issue.evidence && <mark>{issue.evidence}</mark>}
                  {issue.related_id && <code>{issue.related_id}</code>}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
