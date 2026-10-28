import type { ActionPlan } from "../../api/types";

export function isQualityPlan(plan: ActionPlan) {
  return [
    "create_quality_rule",
    "update_quality_rule",
    "delete_quality_rule",
    "run_quality_rule",
    "change_quality_issue",
  ].includes(plan.action_type);
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function text(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function revision(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 1
    ? value
    : null;
}

export function qualityObject(plan: ActionPlan) {
  const params = plan.canonical_params;
  const rule = record(params.rule) ? params.rule : null;
  const target = rule && record(rule.target) ? rule.target : null;
  const issue = plan.action_type === "change_quality_issue";
  return {
    issue,
    id: text(rule?.id) ?? text(issue ? params.issue_id : params.rule_id),
    name: text(rule?.name),
    target: target
      ? [target.source_id, target.schema_name, target.table, target.column]
          .map(text)
          .filter(Boolean)
          .join(" / ")
      : null,
    revision: revision(rule?.revision),
    expectedRevision: revision(params.expected_revision),
    status:
      params.status === "claimed" || params.status === "resolved"
        ? params.status
        : null,
    assignee: text(params.assignee),
  };
}
