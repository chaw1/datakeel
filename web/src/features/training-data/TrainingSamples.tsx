import { useI18n } from "../../i18n/useI18n";

import { TrainingPreview } from "./TrainingPreview";

import type { TrainingRecord } from "../../api/trainingData";

const decisions = {
  keep: "trainingKeep",
  drop: "trainingDrop",
  redact: "trainingRedact",
} as const;

export function TrainingSamples({ samples }: { samples: TrainingRecord[] }) {
  const { t } = useI18n();
  return (
    <section aria-label={t("trainingSamples")}>
      <h3>{t("trainingSamples")}</h3>
      <p className="muted">{t("trainingSamplesHint")}</p>
      {!samples.length && <p>{t("trainingNoSamples")}</p>}
      <div className="training-samples">
        {samples.map((record) => (
          <article
            className="training-record"
            id={`training-${record.id}`}
            key={record.id}
          >
            <h4>
              {t("trainingRecordLocation", {
                file: record.file_id,
                line: record.line,
              })}
            </h4>
            <code className="training-id">{record.id}</code>
            <p className="muted">
              {t("trainingConfidence", {
                confidence: Math.round(record.language_confidence * 100),
                tokens: record.estimated_tokens,
              })}
            </p>
            <TrainingPreview record={record} />
            <p>
              <strong>
                {t("trainingDecision")}: {t(decisions[record.decision])}
              </strong>
            </p>
            {!!record.reasons.length && (
              <p>
                {t("trainingReasons")}: {record.reasons.join(" · ")}
              </p>
            )}
            <ul className="training-findings">
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
