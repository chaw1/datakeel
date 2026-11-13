import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { dataset } from "../../test/fixtures";

import { CopilotDrawer } from "./CopilotDrawer";
import { derivePageContext } from "./pageContext";

import type { Conversation, Dataset } from "../../api/types";
import type { Route } from "../../app/routing";

const datasetFixture: Dataset = {
  ...dataset,
  id: "ds-1",
  name: "Sensor Logs",
};

const sampleConversation: Conversation = {
  id: "conv-1",
  actor: "local",
  created_at: "2026-11-13T00:00:00Z",
  turns: 0,
  messages: [],
  events: [],
  pending_plans: [],
  config: {
    dataset_id: "ds-1",
    provider: "fake",
    model: "fake-demo",
    dry_run: false,
    max_turns: 12,
    max_output_tokens: 1024,
  },
};

function sseStream(events: Array<{ event: string; payload: unknown }>) {
  const body = events
    .map(
      (item) =>
        `event: ${item.event}\ndata: ${JSON.stringify(item.payload)}\n\n`,
    )
    .join("");
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

it("makes zero fetch calls while closed and opens via Ctrl+J without creating a session eagerly", () => {
  const fetchSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);
  const onToggle = vi.fn();
  const route: Route = {
    page: "object",
    params: new URLSearchParams("project_id=proj-9"),
    object: { kind: "dataset", id: "ds-1", tab: "facts" },
  };
  const summary = derivePageContext(route, datasetFixture, "Sensor Logs");

  const { rerender } = render(
    <CopilotDrawer
      open={false}
      summary={summary}
      draftPrompt=""
      onClearDraft={vi.fn()}
      onToggle={onToggle}
      onClose={vi.fn()}
      onOpenReceipt={vi.fn()}
      onDataChanged={vi.fn()}
    />,
  );
  expect(fetchSpy).not.toHaveBeenCalled();

  fireEvent.keyDown(window, { key: "j", ctrlKey: true });
  expect(onToggle).toHaveBeenCalledTimes(1);

  rerender(
    <CopilotDrawer
      open
      summary={summary}
      draftPrompt=""
      onClearDraft={vi.fn()}
      onToggle={onToggle}
      onClose={vi.fn()}
      onOpenReceipt={vi.fn()}
      onDataChanged={vi.fn()}
    />,
  );

  expect(
    screen.getByRole("complementary", { name: "Workspace copilot" }),
  ).toBeVisible();
  expect(screen.getByText("Sensor Logs")).toBeVisible();
  expect(screen.getByText("proj-9")).toBeVisible();
  expect(fetchSpy).not.toHaveBeenCalled();
});

it("lazily creates a conversation on send and respects context toggle", async () => {
  const user = userEvent.setup();
  const postedBodies: unknown[] = [];
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/definitions/provider")) {
      return Promise.resolve(
        Response.json({ provider: "fake", model: "fake-demo" }),
      );
    }
    if (url === "/api/agent/conversations" && init?.method === "POST") {
      return Promise.resolve(Response.json(sampleConversation));
    }
    if (url === "/api/agent/conversations/conv-1/messages") {
      const rawBody = typeof init?.body === "string" ? init.body : "{}";
      postedBodies.push(JSON.parse(rawBody));
      return Promise.resolve(
        sseStream([
          {
            event: "done",
            payload: {
              event: "done",
              id: "ev-done",
              tokens: 5,
              agent_path: "main",
            },
          },
        ]),
      );
    }
    if (url === "/api/agent/conversations/conv-1") {
      return Promise.resolve(Response.json(sampleConversation));
    }
    return Promise.resolve(Response.json({}));
  });
  vi.stubGlobal("fetch", fetchMock);

  const route: Route = {
    page: "labeling",
    params: new URLSearchParams("project_id=proj-1"),
  };
  const summary = derivePageContext(route, datasetFixture);

  render(
    <CopilotDrawer
      open
      summary={summary}
      draftPrompt=""
      onClearDraft={vi.fn()}
      onToggle={vi.fn()}
      onClose={vi.fn()}
      onOpenReceipt={vi.fn()}
      onDataChanged={vi.fn()}
    />,
  );

  const input = screen.getByLabelText("Message");
  await user.type(input, "Check open blockers");
  await user.click(screen.getByRole("button", { name: "Send message" }));

  await waitFor(() => {
    expect(postedBodies).toHaveLength(1);
  });
  const firstBody = postedBodies[0] as {
    content: string;
    context?: Record<string, unknown>;
  };
  expect(firstBody.content).toBe("Check open blockers");
  expect(firstBody.context).toMatchObject({
    dataset_id: "ds-1",
    project_id: "proj-1",
  });

  await user.click(screen.getByRole("button", { name: "Attach current view" }));
  expect(
    screen.getByRole("button", { name: "Context paused" }),
  ).toHaveAttribute("aria-pressed", "false");

  await user.type(screen.getByLabelText("Message"), "Global question");
  await user.click(screen.getByRole("button", { name: "Send message" }));

  await waitFor(() => {
    expect(postedBodies).toHaveLength(2);
  });
  expect((postedBodies[1] as { context?: unknown }).context).toBeUndefined();
});
