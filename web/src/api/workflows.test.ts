import { expect, it, vi } from "vitest";

import { pausedWorkflow, workflowStream } from "../test/workflowFixtures";

import { parseWorkflowEvent, streamWorkflow } from "./workflows";

it("accepts snapshots but rejects a stream that ends before done", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(workflowStream(pausedWorkflow, false))),
  );
  const observe = vi.fn();
  await expect(
    streamWorkflow(
      "/api/workflows/cleanup/runs",
      { inputs: {}, idempotency_key: "start-1" },
      observe,
      new AbortController().signal,
    ),
  ).rejects.toThrow("done event");
  expect(observe).toHaveBeenCalledWith(
    expect.objectContaining({ run: pausedWorkflow }),
  );
});
it("rejects an event name mismatch and malformed snapshots", async () => {
  expect(() => parseWorkflowEvent('{"id":"x","event":"run","run":{}}')).toThrow(
    "Invalid workflow",
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          `event: step\ndata: ${JSON.stringify({ id: "x", event: "done", run: pausedWorkflow })}\n\n`,
          { headers: { "Content-Type": "text/event-stream" } },
        ),
      ),
    ),
  );
  await expect(
    streamWorkflow(
      "/api/workflows/x/runs",
      { inputs: {}, idempotency_key: "x" },
      vi.fn(),
      new AbortController().signal,
    ),
  ).rejects.toThrow("does not match");
});
it("normalizes resume denials without presenting success", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Approval required" }), {
          status: 403,
        }),
      ),
    ),
  );
  await expect(
    streamWorkflow(
      "/api/workflows/runs/x/resume",
      { plan_id: "plan-1", idempotency_key: "resume-1" },
      vi.fn(),
      new AbortController().signal,
    ),
  ).rejects.toThrow("403 Approval required");
});
