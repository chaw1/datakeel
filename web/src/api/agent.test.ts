import { expect, it, vi } from "vitest";

import { agentEvent, eventStream } from "../test/agentFixtures";

import { parseAgentEvent, streamMessage } from "./agent";

it("requires the final done event before declaring a streamed request complete", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(eventStream([agentEvent("text", { text: "partial" })])),
    ),
  );
  const observed = vi.fn();
  await expect(
    streamMessage(
      "conversation-1",
      { content: "hello", idempotency_key: "key-1" },
      observed,
      new AbortController().signal,
    ),
  ).rejects.toThrow("done event");
  expect(observed).toHaveBeenCalledWith(
    expect.objectContaining({ text: "partial" }),
  );
});
it("normalizes server errors before attempting SSE parsing", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Conversation busy" }), {
          status: 409,
        }),
      ),
    ),
  );
  await expect(
    streamMessage(
      "conversation-1",
      { content: "hello", idempotency_key: "key-1" },
      vi.fn(),
      new AbortController().signal,
    ),
  ).rejects.toThrow("409 Conversation busy");
});
it("rejects malformed stream observations", () => {
  expect(() => parseAgentEvent('{"event":"unknown","id":"1"}')).toThrow(
    "Invalid Agent",
  );
  expect(() => parseAgentEvent('{"event":"text","id":"1","text":5}')).toThrow(
    "Invalid Agent",
  );
});

it("does not mistake a child done event for the root stream's completion", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        eventStream([
          agentEvent("done", {
            agent_path: "main/catalog-analyst#1",
            agent_name: "catalog-analyst",
          }),
        ]),
      ),
    ),
  );
  await expect(
    streamMessage(
      "conversation-1",
      { content: "Delegate a review", idempotency_key: "key-child" },
      vi.fn(),
      new AbortController().signal,
    ),
  ).rejects.toThrow("done event");
});
it("continues receiving the main response after a delegated Agent finishes", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        eventStream([
          agentEvent("done", {
            id: "child-done",
            agent_path: "main/catalog-analyst#1",
            agent_name: "catalog-analyst",
          }),
          agentEvent("text", { text: "The delegated review is complete." }),
          agentEvent("done"),
        ]),
      ),
    ),
  );
  const observed = vi.fn();
  await streamMessage(
    "conversation-1",
    { content: "Delegate a review", idempotency_key: "key-root" },
    observed,
    new AbortController().signal,
  );
  expect(observed).toHaveBeenCalledTimes(3);
  expect(observed).toHaveBeenCalledWith(
    expect.objectContaining({ text: "The delegated review is complete." }),
  );
});
