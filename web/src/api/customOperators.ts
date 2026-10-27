import { post } from "./client";

import type { components } from "./generated";
import type { ActionPlan, ActionRun } from "./types";

export type CustomOperatorVersion =
  components["schemas"]["CustomOperatorVersion"];
export type CustomOperatorRun = components["schemas"]["CustomOperatorRun"];
export type CustomOperatorConfiguration =
  components["schemas"]["CustomOperatorConfiguration"];
export type CustomOperatorSubmission =
  components["schemas"]["CustomOperatorSubmission"];
export type StaticCheck = components["schemas"]["StaticCheck"];
export type RunCustomOperatorRequest =
  components["schemas"]["RunCustomOperatorRequest"];

export function submitCustomOperator(body: CustomOperatorSubmission) {
  return post<ActionPlan>("/api/custom-operators", body);
}

export function runCustomOperator(
  codeHash: string,
  body: RunCustomOperatorRequest,
) {
  return post<ActionRun>(
    `/api/custom-operators/${encodeURIComponent(codeHash)}/runs`,
    body,
  );
}
