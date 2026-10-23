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
