import { actionPlan, actionRun } from "./actionFixtures";

import type {
  AgentEvent,
  Conversation,
  ModelCallTrace,
  CostSummary,
} from "../api/types";

export const conversation: Conversation = {
  id: "conversation-1",
  actor: "local",
  created_at: "2026-10-22T12:00:00Z",
  turns: 0,
  config: {
    dataset_id: "dataset-1",
    provider: "fake",
    model: "fake-demo",
    dry_run: false,
    max_turns: 12,
    max_output_tokens: 1024,
    budget: {
      conversation_tokens: 100000,
      daily_tokens: 1000000,
      conversation_usd: "1",
      daily_usd: "10",
    },
  },
  messages: [],
  events: [],
};
export function agentEvent(
  event: AgentEvent["event"],
  changes: Partial<AgentEvent> = {},
): AgentEvent {
  return {
    id: `event-${event}`,
    event,
    text: null,
    call: null,
    outcome: null,
    stop_reason: null,
    ...changes,
  };
}
export const planEvent: AgentEvent = agentEvent("plan", {
  outcome: {
    name: "delete_files",
    status: "SUCCEEDED",
    content: {},
    asset_refs: [],
    plan: actionPlan,
    run: null,
    requires_approval: true,
    error: null,
    invocation_id: "invocation-1",
  },
});
export const completedPlanEvent: AgentEvent = {
  ...planEvent,
  outcome: {
    ...planEvent.outcome,
    name: "delete_files",
    status: "SUCCEEDED",
    content: {},
    asset_refs: [],
    plan: { ...actionPlan, status: "EXECUTED" },
    run: actionRun,
    requires_approval: false,
  },
};
export const toolEvent: AgentEvent = agentEvent("tool_call", {
  call: {
    id: "call-1",
    name: "search_files",
    arguments: { dataset_id: "dataset-1", quality_max: 60 },
  },
});
export const trace: ModelCallTrace = {
  call_type: "conversation",
  billing_status: "actual",
  accounted_tokens: 120,
  budget_exceeded: false,
  id: "trace-1",
  reservation_id: "reservation-1",
  conversation_id: conversation.id,
  turn: 1,
  model: "fake-demo",
  provider: "fake",
  segments: [
    { name: "instructions", tokens: 40, stable: true },
    { name: "history", tokens: 60, stable: false },
  ],
  usage: {
    input_tokens: 100,
    output_tokens: 20,
    cache_read_tokens: 40,
    cache_write_tokens: 10,
  },
  cost_usd: "0.00024",
  price_version: "2026-10-22",
  latency_ms: 12.5,
  stop_reason: "tool_calls",
  tool_calls: 1,
  created_at: "2026-10-22T12:00:00Z",
};
export const cost: CostSummary = {
  unknown_calls: 0,
  unknown_cost_usd: "0",
  key: conversation.id,
  group_by: "conversation",
  calls: 1,
  input_tokens: 100,
  output_tokens: 20,
  cache_read_tokens: 40,
  cache_write_tokens: 10,
  cost_usd: "0.00024",
};
export function eventStream(events: AgentEvent[]): Response {
  const contents = events
    .map((event) => `event: ${event.event}\ndata: ${JSON.stringify(event)}\n\n`)
    .join("");
  return new Response(contents, {
    headers: { "Content-Type": "text/event-stream" },
  });
}
