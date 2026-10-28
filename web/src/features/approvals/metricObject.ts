import type { MetricHistory } from "../../api/objects";
import type { ActionPlan } from "../../api/types";

export function isMetricPlan(plan: ActionPlan) {
  return ["update_metric", "rollback_metric", "confirm_metric_draft"].includes(
    plan.action_type,
  );
}

export function metricObject(plan: ActionPlan) {
  const definition = plan.canonical_params.definition;
  if (
    ["update_metric", "confirm_metric_draft"].includes(plan.action_type) &&
    definition !== null &&
    typeof definition === "object" &&
    !Array.isArray(definition)
  ) {
    const id = "id" in definition ? definition.id : null;
    const name = "name" in definition ? definition.name : null;
    const englishName =
      "english_name" in definition ? definition.english_name : null;
    const version = "version" in definition ? definition.version : null;
    return {
      id: typeof id === "string" ? id : "",
      name: typeof name === "string" ? name : "",
      englishName: typeof englishName === "string" ? englishName : null,
      version: typeof version === "number" ? version : null,
    };
  }
  const id = plan.canonical_params.metric_id;
  return {
    id: typeof id === "string" ? id : "",
    name: typeof id === "string" ? id : "",
    englishName: null,
    version: null,
  };
}

export function metricAtPreparation(plan: ActionPlan, history: MetricHistory) {
  const executed = history.audit.find((item) => item.plan_id === plan.id);
  if (!executed && !hasAuditedVersions(history)) return undefined;
  const preparedAt = preciseTimestamp(plan.created_at);
  if (preparedAt === null) return undefined;
  const later = history.audit.find((item) => {
    const changedAt = preciseTimestamp(item.created_at);
    return changedAt !== null && changedAt >= preparedAt;
  });
  const version = executed?.from_version ?? later?.from_version;
  return version === undefined
    ? history.versions.at(-1)?.definition
    : history.versions.find((item) => item.definition.version === version)
        ?.definition;
}

function hasAuditedVersions(history: MetricHistory) {
  return history.versions.every(({ definition }, index, versions) => {
    if (index === 0) return definition.version === 1;
    const previous = versions[index - 1].definition.version;
    return (
      definition.version === previous + 1 &&
      history.audit.some(
        (item) =>
          item.from_version === previous &&
          item.to_version === definition.version,
      )
    );
  });
}

function preciseTimestamp(value: string) {
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) return null;
  const fraction = /\.(\d+)(?:Z|[+-]\d{2}:\d{2})$/.exec(value)?.[1] ?? "";
  const microseconds = fraction.padEnd(6, "0").slice(3, 6);
  return BigInt(milliseconds) * 1000n + BigInt(microseconds);
}
