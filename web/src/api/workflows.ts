import { readServerSentEvents } from "../lib/sse";

import { requireSuccess } from "./client";

import type { components } from "./generated";

export type WorkflowDefinition = components["schemas"]["WorkflowDefinition"];
export type WorkflowInput = components["schemas"]["WorkflowInput"];
export type WorkflowStart = components["schemas"]["WorkflowStart"];
export type WorkflowRun = components["schemas"]["WorkflowRun"];
export type WorkflowEvent = components["schemas"]["WorkflowEvent"];
export type WorkflowResume = components["schemas"]["ResumeInput"];

export function parseWorkflowEvent(data: string): WorkflowEvent {
  const value: unknown = JSON.parse(data);
  if (
    !value ||
    typeof value !== "object" ||
    !("id" in value) ||
    typeof value.id !== "string" ||
    !("event" in value) ||
    !["run", "step", "done"].includes(String(value.event)) ||
    !("run" in value) ||
    !value.run ||
    typeof value.run !== "object" ||
    !("id" in value.run) ||
    typeof value.run.id !== "string"
  )
    throw new Error("Invalid workflow stream event");
  return value as WorkflowEvent;
}

export async function streamWorkflow(
  path: string,
  body: WorkflowStart | WorkflowResume,
  onEvent: (event: WorkflowEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal,
  });
  await requireSuccess(response);
  if (
    !response.body ||
    !response.headers.get("Content-Type")?.includes("text/event-stream")
  )
    throw new Error("Expected a workflow event stream");
  let complete = false;
  for await (const frame of readServerSentEvents(response.body)) {
    const event = parseWorkflowEvent(frame.data);
    if (frame.event !== "message" && frame.event !== event.event)
      throw new Error("Workflow event name does not match payload");
    onEvent(event);
    if (event.event === "done") complete = true;
  }
  if (!complete) throw new Error("Workflow stream ended before the done event");
}
