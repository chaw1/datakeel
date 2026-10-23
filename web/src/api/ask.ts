import { get, post } from "./client";

import type { components } from "./generated";

export type AskAnswer = components["schemas"]["AskAnswer"];
export type AskRequest = components["schemas"]["AskRequest"];
export type AskMetric = components["schemas"]["MetricCard"];
export type AskMatch = components["schemas"]["MatchEvidence"];
export type AskResult = components["schemas"]["QueryResult"];

export function askData(request: AskRequest): Promise<AskAnswer> {
  return post<AskAnswer>("/api/ask", request);
}

export function replayAnswer(id: string): Promise<AskAnswer> {
  return get<AskAnswer>(`/api/ask/${encodeURIComponent(id)}`);
}
