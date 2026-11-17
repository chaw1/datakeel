import { Icon } from "../../components/Icon";
import { Badge, EmptyState } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { display } from "../../lib/format";

import {
  qualityDimensions as labels,
  qualityGrade,
  qualityIssueMessage,
  qualitySeverity,
} from "./labels";
import { QualityScore } from "./QualityScore";

import type { Quality as QualityData } from "../../api/types";
export default function Quality({
  quality,
  compact = false,
}: {
  quality: QualityData | null;
  compact?: boolean;
}) {
  const { t } = useI18n();

  if (!quality)
    return (
      <EmptyState
        icon="quality"
        title={t("qualityIsOnItsWay")}
        description={t("scoresAndIssuesAppearAfterTheDatasetIsAnalyzed")}
      />
    );
  const dimensions = Object.entries(quality.dimensions);
  const issues = quality.issues;
  return (
    <div className={`quality-content ${compact ? "compact-quality" : ""}`}>
      <div className="quality-summary">
        <QualityScore quality={quality} />
        <div>
          <Badge
            tone={
              quality.grade === "poor"
                ? "danger"
                : quality.grade === "fair"
                  ? "warn"
                  : "ok"
            }
          >
            {qualityGrade(quality.grade, t)}
          </Badge>
          <h3>{t("aClearerPictureOfYourData")}</h3>
          <p>
            {t("fiveDimensionsOneWeightedScore")} <br />
            {t("everyFindingComesWithANextStep")}{" "}
          </p>
        </div>
      </div>
      <div className="dimension-list">
        {dimensions.map(([key, value]) => {
          const detail = value;
          const excluded = !detail.included;
          return (
            <div className="dimension" key={key}>
              <div className="dimension-heading">
                <span>
                  {key in labels ? t(labels[key]) : key.replaceAll("_", " ")}
                  {excluded && <span className="muted">{t("excluded")}</span>}
                </span>
                <strong>{excluded ? t("nA") : value.score.toFixed(1)}</strong>
              </div>
              <div className="bar">
                <span
                  style={{ width: excluded ? 0 : `${String(value.score)}%` }}
                />
              </div>
              {!compact && (
                <p className="small muted">
                  {excluded
                    ? t("noAnnotationEvidenceRemainingWeightsAreNormalized")
                    : t("weightedScore", {
                        weight: detail.weight.toFixed(1),
                      })}
                </p>
              )}
              {!compact && (
                <details className="measurement-details">
                  <summary>{t("measurementEvidence")}</summary>
                  <pre>
                    {typeof detail.details === "string"
                      ? detail.details
                      : JSON.stringify(detail.details, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          );
        })}
      </div>
      {!compact && (
        <section className="issues-section">
          <div className="section-heading">
            <h3>
              {t("qualityFindings")}{" "}
              <span className="count-pill">{issues.length}</span>
            </h3>
            <span className="muted small">{t("prioritizedForAction")}</span>
          </div>
          {issues.length ? (
            <div className="issue-list">
              {issues.map((issue, index) => (
                <article className="issue" key={index}>
                  <Badge
                    tone={
                      issue.severity === "critical"
                        ? "danger"
                        : issue.severity === "warning"
                          ? "warn"
                          : "neutral"
                    }
                  >
                    {qualitySeverity(issue.severity, t)}
                  </Badge>
                  <div>
                    <h4>{qualityIssueMessage(issue, quality.dimensions, t)}</h4>
                    {issue.dimension ? (
                      <span className="small muted">
                        {issue.dimension in labels
                          ? t(labels[issue.dimension])
                          : display(issue.dimension)}
                      </span>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="all-clear">
              <Icon name="check" />
              {t("noQualityIssuesFoundWithTheCurrentThresholds")}{" "}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
