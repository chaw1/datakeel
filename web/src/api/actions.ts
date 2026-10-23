import { post } from "./client";

import type { components } from "./generated";
import type { ActionPlan, ActionRun } from "./types";

export function decidePlan(plan: ActionPlan, approve: boolean) {
  const body: components["schemas"]["ApprovalDecision"] = {
    approve,
    plan_digest: plan.plan_digest,
    actor: "local",
    reason: "",
  };
  return post<ActionPlan>(
    `/api/approvals/${encodeURIComponent(plan.id)}`,
    body,
  );
}
export function executePlan(plan: ActionPlan) {
  const body: components["schemas"]["ExecuteRequest"] = {
    plan_digest: plan.plan_digest,
    actor: "local",
    operation_id: plan.operation_id,
  };
  return post<ActionRun>(
    `/api/actions/${encodeURIComponent(plan.id)}/execute`,
    body,
  );
}
