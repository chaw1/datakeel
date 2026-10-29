import { post, ApiError } from "../../api/client";

import type { components } from "../../api/generated";
import type { ActionPlan, ActionRun } from "../../api/types";

type ActionName = ActionPlan["action_type"];
type Json = components["schemas"]["JsonValue"];

export async function prepareProduction(
  name: ActionName,
  values: Record<string, Json>,
) {
  return post<ActionPlan>(`/api/actions/${name}/prepare`, {
    request_id: crypto.randomUUID(),
    ...values,
  });
}

export async function executeProduction(plan: ActionPlan, approve = false) {
  if (approve) {
    await post<ActionPlan>(`/api/approvals/${encodeURIComponent(plan.id)}`, {
      approve: true,
      plan_digest: plan.plan_digest,
      actor: plan.actor,
      reason: "",
    } satisfies components["schemas"]["ApprovalDecision"]);
  }
  const run = await post<ActionRun>(
    `/api/actions/${encodeURIComponent(plan.id)}/execute`,
    {
      actor: plan.actor,
      plan_digest: plan.plan_digest,
      operation_id: plan.operation_id,
    } satisfies components["schemas"]["ExecuteRequest"],
  );
  if (run.status !== "SUCCEEDED") {
    throw new ApiError(
      run.status === "DENIED" ? 403 : 409,
      run.error ?? run.reason ?? run.status,
    );
  }
  return run;
}

export async function mutateProduction(
  name: ActionName,
  values: Record<string, Json>,
) {
  const plan = await prepareProduction(name, values);
  if (!plan.reversible || plan.external)
    throw new ApiError(409, "Human approval required");
  return executeProduction(plan);
}

export function actionDetails(run: ActionRun): unknown {
  return run.receipt?.quality?.details;
}
