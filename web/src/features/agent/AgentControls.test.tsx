import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AgentPage } from "../../pages/AgentPage";
import {
  agentEvent,
  conversation,
  completedPlanEvent,
  eventStream,
} from "../../test/agentFixtures";
import { dataset } from "../../test/fixtures";

import type { Conversation } from "../../api/types";

const props = {
  datasets: [dataset],
  datasetId: dataset.id,
  conversationId: conversation.id,
  onConversation: vi.fn(),
  onDataChanged: vi.fn(),
  onOpenReceipt: vi.fn(),
  onTrace: vi.fn(),
};
function withMessage(events: Conversation["events"]): Conversation {
  return {
    ...conversation,
    messages: [
      { role: "user", content: "Inspect low quality files", tool_calls: [] },
    ],
    events,
    turns: 1,
  };
}
function json(value: unknown) {
  return Response.json(value);
}

it("resumes the approved pause through its own endpoint without posting a message", async () => {
  const pause = [
    completedPlanEvent,
    agentEvent("stopped", { stop_reason: "approval_required" }),
    agentEvent("done"),
  ];
  const resumed = [
    agentEvent("receipt", { outcome: completedPlanEvent.outcome }),
    agentEvent("text", { text: "Continued safely" }),
    agentEvent("done", { id: "resumed-done" }),
  ];
  let continued = false;
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    if (path.endsWith("/resume") && init?.method === "POST") {
      continued = true;
      return Promise.resolve(eventStream(resumed));
    }
    const current = withMessage(continued ? [...pause, ...resumed] : pause);
    return Promise.resolve(
      json(path === "/api/agent/conversations" ? [current] : current),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<AgentPage {...props} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue conversation" }),
  );
  expect(await screen.findByText("Continued safely")).toBeVisible();
  await waitFor(() => {
    expect(screen.getByLabelText("Message")).toBeEnabled();
  });
  expect(
    screen.queryByRole("button", { name: "Continue conversation" }),
  ).toBeNull();
  const posts = fetch.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(1);
  expect(posts[0][0]).toBe(
    `/api/agent/conversations/${conversation.id}/resume`,
  );
  const resumedBody = posts[0][1]?.body;
  if (typeof resumedBody !== "string") throw new Error("Missing resume body");
  expect(resumedBody).toContain('"plan_id":"plan-1"');
  expect(resumedBody).toMatch(/"idempotency_key":"[\w-]+"/);
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/tree"))).toBe(false);
});

it("escalates an unsupported planner request with agent mode", async () => {
  const events = [
    agentEvent("intent", {
      intent: {
        kind: "unsupported",
        text: "More investigation is needed",
        request: "Investigate everything",
        parser: "rules",
        chain: null,
        clarification: null,
        answer: null,
        missing_scopes: [],
        draft: {},
      },
    }),
    agentEvent("done"),
  ];
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    if (path.endsWith("/messages") && init?.method === "POST")
      return Promise.resolve(eventStream([agentEvent("done")]));
    return Promise.resolve(
      json(
        path === "/api/agent/conversations"
          ? [withMessage(events)]
          : withMessage(events),
      ),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<AgentPage {...props} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Ask Deep Agent instead" }),
  );
  await waitFor(() => {
    expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
      true,
    );
  });
  const body = fetch.mock.calls.find(([, init]) => init?.method === "POST")?.[1]
    ?.body;
  if (typeof body !== "string") throw new Error("Missing message body");
  expect(JSON.parse(body)).toMatchObject({
    content: "Investigate everything",
    mode: "agent",
    context: { dataset_id: dataset.id },
  });
});
