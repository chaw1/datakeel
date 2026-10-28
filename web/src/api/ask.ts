import { get, post, requireSuccess } from "./client";

import type { components } from "./generated";

export type AskAnswer = components["schemas"]["AskAnswer"];
export type AskConversation = components["schemas"]["AskConversation"];
export type ProfileAnswer = components["schemas"]["ProfileAnswer"];
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

export function replayAnswer(
  id: string,
  actor = "local-user",
): Promise<AskAnswer> {
  return get<AskAnswer>(`/api/ask/${encodeURIComponent(id)}`, {
    "X-Datakeel-Actor": actor,
  });
}

export function listAskConversations(
  actor: string,
): Promise<AskConversation[]> {
  return get<AskConversation[]>("/api/ask/conversations", {
    "X-Datakeel-Actor": actor,
  });
}

export function openAskConversation(
  id: string,
  actor: string,
): Promise<AskConversation> {
  return get<AskConversation>(
    `/api/ask/conversations/${encodeURIComponent(id)}`,
    { "X-Datakeel-Actor": actor },
  );
}

export async function deleteAskConversation(
  id: string,
  actor: string,
): Promise<void> {
  const response = await fetch(
    `/api/ask/conversations/${encodeURIComponent(id)}`,
    { method: "DELETE", headers: { "X-Datakeel-Actor": actor } },
  );
  await requireSuccess(response);
}
