import { get, post } from "./client";

import type { components } from "./generated";

export type AskAnswer = components["schemas"]["AskAnswer"];
export type AskRequest = components["schemas"]["AskRequest"];
export type AskMetric = components["schemas"]["MetricCard"];
export type AskMatch = components["schemas"]["MatchEvidence"];
export type AskResult = components["schemas"]["QueryResult"];
export type KnowledgeAnswer = components["schemas"]["KnowledgeAnswer"];
export type KnowledgeClaim = components["schemas"]["KnowledgeClaim"];
export type KnowledgeSubject = components["schemas"]["KnowledgeSubject"];
export type KnowledgeIntent = KnowledgeAnswer["intent"];
export type SelectedKnowledgeIntent = NonNullable<
  AskRequest["knowledge_intent"]
>;
export type KnowledgeRecognition =
  components["schemas"]["KnowledgeRecognition"];

export function askData(request: AskRequest): Promise<AskAnswer> {
  return post<AskAnswer>("/api/ask", request);
}

export function replayAnswer(id: string): Promise<AskAnswer> {
  return get<AskAnswer>(`/api/ask/${encodeURIComponent(id)}`);
}
