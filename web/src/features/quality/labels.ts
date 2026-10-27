import type { Quality } from "../../api/types";
import type { Translate } from "../../i18n/context";
import type { MessageKey } from "../../i18n/en";

export const qualityDimensions: Record<string, MessageKey> = {
  database_rules: "databaseRules",
  completeness: "completeness",
  consistency: "consistency",
  uniqueness: "uniqueness",
  annotation: "annotation",
  distribution: "distribution",
  distribution_health: "distribution",
};
const grades: Record<string, MessageKey> = {
  excellent: "qualityExcellent",
  good: "qualityGood",
  fair: "qualityFair",
  poor: "qualityPoor",
};
const severities: Record<string, MessageKey> = {
  critical: "qualityCritical",
  warning: "qualityWarning",
  info: "info",
};

export function qualityGrade(
  grade: string | undefined,
  t: Translate,
  fallback: MessageKey = "scored",
): string {
  return grade && grade in grades ? t(grades[grade]) : t(fallback);
}

export function qualitySeverity(severity: string, t: Translate): string {
  return t(severities[severity] ?? "info");
}

export function qualityIssueMessage(
  issue: Quality["issues"][number],
  dimensions: Quality["dimensions"],
  t: Translate,
): string {
  if (issue.code === "annotation_excluded")
    return t("noAnnotationEvidenceRemainingWeightsAreNormalized");
  if (issue.code === "empty_dataset") return t("qualityNoFiles");
  const dimension = issue.dimension;
  if (
    dimension &&
    dimension in qualityDimensions &&
    issue.code === `${dimension}_below_target` &&
    dimension in dimensions
  )
    return t("qualityBelowTarget", {
      dimension: t(qualityDimensions[dimension]),
      score: dimensions[dimension].score.toFixed(2),
    });
  return issue.message || t("qualityFinding");
}
