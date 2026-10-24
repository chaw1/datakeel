import { post } from "./client";

import type { components } from "./generated";
import type { ActionRun, DecideAssertionsParams } from "./types";

export type KGQuery = components["schemas"]["KGQuery"];
export type KGResult = components["schemas"]["KGQueryResult"];
export type KGEntity = components["schemas"]["KGEntityView"];
export type KGRelation = components["schemas"]["KGRelationView"];
export type KGExplanation = components["schemas"]["KGRelationExplanation"];
export type KGSource = components["schemas"]["KGSourceText"];
export type KGGraph = components["schemas"]["KGGraph"];
export type KGRun = components["schemas"]["KGRun"];
export type KGEvaluation = components["schemas"]["KGEvalReport"];
export type KGSchema = components["schemas"]["KGSchema"];
export type KGProfile = components["schemas"]["ExtractionProfile"];

export function decideRelations(
  assertionIds: string[],
  status: "accepted" | "rejected",
  reason: string,
) {
  return post<ActionRun>("/api/evidence/assertions/decide", {
    assertion_ids: assertionIds,
    status,
    reason,
  } satisfies DecideAssertionsParams);
}
