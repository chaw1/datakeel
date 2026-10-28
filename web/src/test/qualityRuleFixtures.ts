import { vi } from "vitest";

import { actionPlan, actionRun } from "./actionFixtures";

import type {
  DqIssue,
  DqResult,
  DqRule,
  DqRuleView,
} from "../api/qualityRules";
import type { ActionPlan } from "../api/types";

export const dqRule: DqRule = {
  id: "orders-amount",
  name: "Orders amount must be positive",
  target: {
    source_id: "ecommerce",
    schema_name: "main",
    table: "orders",
    column: "paid_amount",
  },
  kind: "range",
  params: {
    minimum: 0,
    baseline_runs: 3,
    bin_edges: [-100, 0, 10, 100, 1000],
    statistic: "mean",
    values: [],
  },
  owner: "Commerce team",
  revision: 2,
  severity: "error",
  threshold: 0,
  cron: "0 9 * * *",
  timeout_ms: 5000,
  max_rows: 10000,
  enabled: true,
};

export const dqResult: DqResult = {
  id: "result-1",
  rule_id: dqRule.id,
  rule_revision: 2,
  status: "failed",
  actual_value: 1,
  threshold: 0,
  row_count: 100,
  failed_count: 1,
  samples: [{ row_number: 2, column: "paid_amount", value: "[REDACTED]" }],
  metrics: {
    row_count: 100,
    mean: 20,
    null_rate: 0,
    bin_edges: [],
    histogram: [],
  },
  started_at: "2026-10-27T09:00:00Z",
  duration_ms: 2.5,
  message: "Observed one violating row.",
  passed: false,
};

export const dqView: DqRuleView = {
  rule: dqRule,
  latest_result: dqResult,
  next_due_at: "2026-10-28T09:00:00Z",
};

export const dqIssue: DqIssue = {
  id: "issue-1",
  rule_id: dqRule.id,
  status: "open",
  can_resolve: false,
  assignee: null,
  failures: 3,
  first_result_id: "result-1",
  last_result_id: "result-3",
  revision: 3,
  created_at: "2026-10-25T09:00:00Z",
  updated_at: "2026-10-27T09:00:00Z",
};

export function mockQualityRulesApi(retired = false) {
  let views = retired ? [] : [dqView];
  let issue = { ...dqIssue, can_resolve: retired };
  let plan: ActionPlan = { ...actionPlan, action_type: "update_quality_rule" };
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    if (path.endsWith("/prepare")) {
      const body = JSON.parse(
        typeof init?.body === "string" ? init.body : "{}",
      ) as Record<string, unknown>;
      const action = path.split("/")[3] as ActionPlan["action_type"];
      plan = {
        ...actionPlan,
        action_type: action,
        canonical_params: body,
        reversible: ["run_quality_rule", "change_quality_issue"].includes(
          action,
        ),
      };
      return Promise.resolve(new Response(JSON.stringify(plan)));
    }
    if (path.includes("/api/approvals/"))
      return Promise.resolve(
        new Response(JSON.stringify({ ...plan, status: "APPROVED" })),
      );
    if (path.endsWith("/execute")) {
      if (plan.action_type === "delete_quality_rule") views = [];
      if (plan.action_type === "change_quality_issue")
        issue = {
          ...issue,
          status:
            plan.canonical_params.status === "resolved"
              ? "resolved"
              : "claimed",
          assignee: "local",
          can_resolve: false,
          revision: issue.revision + 1,
        };
      return Promise.resolve(
        new Response(
          JSON.stringify({ ...actionRun, action_type: plan.action_type }),
        ),
      );
    }
    if (path.includes("/results"))
      return Promise.resolve(
        new Response(
          JSON.stringify([
            dqResult,
            {
              ...dqResult,
              id: "result-0",
              status: "baseline_insufficient",
              message: "Baseline needs more observations.",
              samples: [],
              actual_value: 0.5,
              started_at: "2026-10-26T09:00:00Z",
              passed: null,
            },
          ]),
        ),
      );
    if (path.includes("/issues"))
      return Promise.resolve(new Response(JSON.stringify([issue])));
    return Promise.resolve(new Response(JSON.stringify(views)));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
