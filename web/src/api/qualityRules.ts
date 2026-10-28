import { post } from "./client";

import type { components } from "./generated";
import type { ActionPlan } from "./types";

export type DqRule = components["schemas"]["DqRule"];
export type DqRuleView = components["schemas"]["DqRuleView"];
export type DqResult = components["schemas"]["DqResult"];
export type DqIssue = components["schemas"]["DqIssue"];
export type DqParameters = components["schemas"]["DqParameters"];

export function qualityRulesPath(filters?: {
  source_id?: string;
  table?: string;
  schema_name?: string;
}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters ?? {}))
    if (value) query.set(key, value);
  return `/api/quality/rules${query.size ? `?${query.toString()}` : ""}`;
}

export function qualityResultsPath(id: string) {
  return `/api/quality/rules/${encodeURIComponent(id)}/results?limit=50`;
}

export function qualityIssuesPath(id: string) {
  return `/api/quality/issues?${new URLSearchParams({ rule_id: id }).toString()}`;
}

export function prepareRule(rule: DqRule, existing: boolean) {
  return post<ActionPlan>(
    `/api/actions/${existing ? "update_quality_rule" : "create_quality_rule"}/prepare`,
    existing ? { rule, expected_revision: rule.revision } : { rule },
  );
}

export function prepareDeleteRule(rule: DqRule) {
  return post<ActionPlan>("/api/actions/delete_quality_rule/prepare", {
    rule_id: rule.id,
    expected_revision: rule.revision,
  });
}

export function prepareRunRule(ruleId: string) {
  return post<ActionPlan>("/api/actions/run_quality_rule/prepare", {
    rule_id: ruleId,
  });
}

export function prepareQualityIssue(
  issue: DqIssue,
  status: "claimed" | "resolved",
  assignee: string | null,
) {
  return post<ActionPlan>("/api/actions/change_quality_issue/prepare", {
    issue_id: issue.id,
    expected_revision: issue.revision,
    status,
    assignee,
  });
}
