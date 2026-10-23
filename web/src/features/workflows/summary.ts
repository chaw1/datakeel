import { stepLabel } from "./labels";

import type { WorkflowRun } from "../../api/workflows";
import type { Locale, Translate } from "../../i18n/context";
import type { MessageKey } from "../../i18n/en";

type Step = WorkflowRun["steps"][number];

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function count(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}

function length(value: unknown): number | undefined {
  return Array.isArray(value) ? value.length : undefined;
}

function numbered(
  key: MessageKey,
  value: unknown,
  t: Translate,
): string | null {
  const number = count(value);
  return number === undefined ? null : t(key, { count: number });
}

export function workflowStepTitle(step: Step, locale: Locale, t: Translate) {
  return step.title?.[locale] ?? stepLabel(step.type, t);
}

function rowsSummary(
  rows: unknown,
  locale: Locale,
  t: Translate,
): string | null {
  if (!Array.isArray(rows)) return null;
  if (rows.length === 1 && Array.isArray(rows[0]) && rows[0].length === 1) {
    const scalar: unknown = rows[0][0];
    if (typeof scalar === "number" && Number.isFinite(scalar))
      return new Intl.NumberFormat(locale, {
        maximumFractionDigits: 20,
      }).format(scalar);
    if (typeof scalar === "string" && scalar.length <= 80) return scalar;
    if (scalar === null) return t("workflowNoValue");
  }
  return t("workflowResultRows", { count: rows.length });
}

function comparisonSummary(
  output: Record<string, unknown>,
  locale: Locale,
  t: Translate,
) {
  if (typeof output.rows_equal !== "boolean") return null;
  const before = rowsSummary(output.before_rows, locale, t);
  const after = rowsSummary(output.after_rows, locale, t);
  if (before === null || after === null) return null;
  return t("workflowComparisonSummary", {
    before,
    after,
    result: t(
      output.rows_equal ? "workflowAnswerUnchanged" : "workflowAnswerChanged",
    ),
  });
}

function conclusionSummary(
  output: Record<string, unknown>,
  locale: Locale,
  t: Translate,
) {
  if (output.conclusion === "cleaned")
    return (
      numbered("workflowCleanedSummary", output.file_count, t) ??
      t("workflowCleaned")
    );
  if (output.conclusion === "no_low_quality_files")
    return t("workflowNoLowQualityFiles");
  if (output.conclusion === "healthy" || output.conclusion === "needs_review") {
    const conclusion = t(
      output.conclusion === "healthy"
        ? "workflowHealthy"
        : "workflowNeedsReview",
    );
    const score = count(output.total);
    return score === undefined
      ? conclusion
      : t("workflowHealthSummary", { conclusion, score });
  }
  return comparisonSummary(output, locale, t);
}

function readSummary(
  tool: unknown,
  data: Record<string, unknown>,
  locale: Locale,
  t: Translate,
) {
  switch (tool) {
    case "search_files":
      return numbered("workflowFoundFiles", length(data.objects), t);
    case "get_quality":
      return numbered("workflowQualityScore", data.total, t);
    case "get_report":
      return numbered("workflowReportSummary", length(data.chapters), t);
    case "query_evidence":
      return numbered("workflowEvidenceSummary", data.total, t);
    case "explain_metric": {
      const definition = record(data.definition);
      return typeof definition.name === "string" &&
        count(definition.version) !== undefined
        ? t("workflowMetricSummary", {
            name: definition.name,
            version: Number(definition.version),
          })
        : null;
    }
    case "impact_of":
      return numbered(
        data.truncated ? "workflowImpactTruncated" : "workflowImpactSummary",
        length(data.objects),
        t,
      );
    case "ask_data": {
      if (data.status === "unanswerable") return t("workflowAnswerUnavailable");
      if (data.status === "clarification")
        return t("workflowAnswerClarification");
      const answer = rowsSummary(record(data.result).rows, locale, t);
      return data.status === "answered" && answer !== null
        ? t("workflowAnswerSummary", { answer })
        : null;
    }
    default:
      return null;
  }
}

function actionSummary(
  output: Record<string, unknown>,
  tool: unknown,
  t: Translate,
) {
  if (tool === "run_pipeline" && typeof output.task_id === "string")
    return t("workflowPipelineQueued");
  if (output.status !== "SUCCEEDED") return null;
  const quality = record(record(output.receipt).quality);
  if (tool === "quarantine_files")
    return numbered("workflowQuarantinedFiles", quality.object_count, t);
  if (tool === "delete_files")
    return numbered("workflowDeletedFiles", quality.object_count, t);
  if (tool === "update_metric") return t("workflowMetricUpdated");
  return null;
}

export function workflowStepSummary(
  step: Step,
  run: WorkflowRun,
  locale: Locale,
  t: Translate,
): string {
  if (step.status === "PENDING" && run.status === "FAILED")
    return t("workflowNotRunFailed");
  if (step.status === "PENDING" && run.status === "INTERRUPTED")
    return t("workflowNotRunInterrupted");
  const states: Partial<Record<Step["status"], MessageKey>> = {
    PENDING: "workflowStepPending",
    RUNNING: "workflowStepRunning",
    PAUSED: "workflowStepPaused",
    SKIPPED: "workflowStepSkipped",
    FAILED: "workflowStepFailed",
  };
  const state = states[step.status];
  if (state) return t(state);
  const output = record(step.output);
  if (step.type === "branch" && typeof output.matched === "boolean") {
    const next = run.steps.find((candidate) => candidate.id === output.next);
    return next
      ? t(
          output.matched
            ? "workflowConditionMatched"
            : "workflowConditionUnmatched",
          { next: workflowStepTitle(next, locale, t) },
        )
      : t(output.matched ? "workflowConditionTrue" : "workflowConditionFalse");
  }
  if (step.type === "wait" && output.state === "COMPLETED")
    return t("workflowTaskCompleted");
  if (step.type === "output")
    return conclusionSummary(output, locale, t) ?? t("workflowConclusionReady");
  const tool = output.function ?? output.action_type ?? step.tool;
  return (
    readSummary(tool, record(output.data), locale, t) ??
    actionSummary(output, tool, t) ??
    t("workflowStepCompleted")
  );
}
