import { readServerSentEvents } from "../lib/sse";

import { post, requireSuccess } from "./client";

import type {
  AgentEvent,
  Conversation,
  ConversationCreate,
  MessageInput,
} from "./types";

const events: AgentEvent["event"][] = [
  "text",
  "tool_call",
  "tool_result",
  "plan",
  "receipt",
  "stopped",
  "done",
];
export function parseAgentEvent(data: string): AgentEvent {
  const value: unknown = JSON.parse(data);
  if (
    !value ||
    typeof value !== "object" ||
    !("event" in value) ||
    !("id" in value) ||
    typeof value.id !== "string" ||
    !events.some((event) => event === value.event)
  )
    throw new Error("Invalid Agent stream event");
  if ("text" in value && value.text !== null && typeof value.text !== "string")
    throw new Error("Invalid Agent text event");
  return value as AgentEvent;
}
export function createConversation(
  datasetId: string,
  dryRun: boolean,
  budget: ConversationCreate["budget"],
) {
  const body: ConversationCreate = {
    dataset_id: datasetId || null,
    provider: "fake",
    model: "fake-demo",
    dry_run: dryRun,
    budget,
    max_turns: 12,
    max_output_tokens: 1024,
  };
  return post<Conversation>("/api/agent/conversations", body);
}
export async function streamMessage(
  id: string,
  body: MessageInput,
  onEvent: (event: AgentEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `/api/agent/conversations/${encodeURIComponent(id)}/messages`,
    {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal,
    },
  );
  await requireSuccess(response);
  if (
    !response.body ||
    !response.headers.get("Content-Type")?.includes("text/event-stream")
  )
    throw new Error("Expected an Agent event stream");
  let complete = false;
  for await (const frame of readServerSentEvents(response.body)) {
    const event = parseAgentEvent(frame.data);
    if (frame.event !== "message" && frame.event !== event.event)
      throw new Error("Agent event name does not match payload");
    onEvent(event);
    if (event.event === "done") complete = true;
  }
  if (!complete) throw new Error("Agent stream ended before the done event");
}
