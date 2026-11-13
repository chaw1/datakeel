import { get, post } from "./client";

import type { components } from "./generated";

export type ActionChain = components["schemas"]["ActionChain"];
export type ChainStep = components["schemas"]["ChainStep"];
export type IntentResult = components["schemas"]["IntentResult"];
export type PageContext = components["schemas"]["PageContext"];
export type LabelSet = components["schemas"]["LabelSet"];
export type LabelGuidelines = components["schemas"]["LabelGuidelines"];
type FunctionResult = components["schemas"]["FunctionResult"];

const chainPath = (id: string) =>
  `/api/intents/chains/${encodeURIComponent(id)}`;

export function readChain(id: string) {
  return get<ActionChain>(chainPath(id));
}

/** Confirm, continue after a signature, or resume after a failed step. */
export function runChain(id: string) {
  return post<ActionChain>(`${chainPath(id)}/run`, {});
}

/** Replan failed steps or plan deferred steps against live state without running. */
export function replanChain(id: string, context?: PageContext) {
  return post<IntentResult>(
    `${chainPath(id)}/replan`,
    context ? { context } : {},
  );
}

export async function readLabelSet(
  id: string,
  version: number,
): Promise<LabelSet> {
  const query = new URLSearchParams({
    object_id: id,
    version: String(version),
  });
  const result = await get<FunctionResult>(
    `/api/production/objects/label_set?${query.toString()}`,
  );
  const rows: unknown[] = Array.isArray(result.data) ? result.data : [];
  const first = rows.at(0);
  if (!first || typeof first !== "object" || !("properties" in first))
    throw new Error("Label set version not found");
  return first.properties as LabelSet;
}
