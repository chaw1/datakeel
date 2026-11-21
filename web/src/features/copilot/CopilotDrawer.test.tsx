import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { dataset } from "../../test/fixtures";

import { CopilotDrawer } from "./CopilotDrawer";
import { derivePageContext } from "./pageContext";

import type { CallTree, Conversation, Dataset } from "../../api/types";
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
    budget: {
      conversation_tokens: 1000,
      conversation_usd: "0.1",
      daily_tokens: 10000,
      daily_usd: "1",
    },
  },
};
const callTree: CallTree = {
  nodes: [
    {
      id: "child-1",
      root_id: "conv-1",
      parent_id: "conv-1",
      parent_tool_call_id: "tool-1",
      agent_name: "inspector",
      agent_path: "main/inspector",
      depth: 1,
      tokens: 420,
      cost_usd: "0.025",
      model_calls: 2,
      tool_elapsed_ms: 30,
      failed_tools: 1,
      tools: ["search_files"],
    },
  ],
  traces: [],
  models: ["fake-demo"],
  total_tokens: 420,
  total_cost_usd: "0.025",
  total_tool_calls: 3,
  total_tool_elapsed_ms: 30,
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

it("creates on send, respects context, and lazily reveals exportable session telemetry", async () => {
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
    if (url === "/api/agent/conversations/conv-1/tree") {
      return Promise.resolve(Response.json(callTree));
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
  await user.selectOptions(screen.getByLabelText("Execution mode"), "agent");
  await user.type(input, "Check open blockers");
  await user.click(screen.getByRole("button", { name: "Send message" }));

  await waitFor(() => {
    expect(postedBodies).toHaveLength(1);
  });
  const firstBody = postedBodies[0] as {
    content: string;
    mode?: string;
    context?: Record<string, unknown>;
  };
  expect(firstBody.content).toBe("Check open blockers");
  expect(firstBody.mode).toBe("agent");
  expect(firstBody.context).toMatchObject({
    dataset_id: "ds-1",
    project_id: "proj-1",
  });

  await user.click(screen.getByRole("button", { name: "Attach current view" }));
  expect(
    screen.getByRole("button", { name: "Context paused" }),
  ).toHaveAttribute("aria-pressed", "false");

  await user.type(screen.getByLabelText("Message"), "Global question");
  await user.selectOptions(screen.getByLabelText("Execution mode"), "plan");
  await user.click(screen.getByRole("button", { name: "Send message" }));

  await waitFor(() => {
    expect(postedBodies).toHaveLength(2);
  });
  expect((postedBodies[1] as { context?: unknown }).context).toBeUndefined();
  expect((postedBodies[1] as { mode?: string }).mode).toBe("plan");
  const report = screen.getByRole("link", {
    name: "Export conversation report",
  });
  expect(report).toHaveAttribute(
    "href",
    "/api/agent/conversations/conv-1/export?format=markdown",
  );
  expect(report).toHaveAttribute("download");
  expect(fetchMock.mock.calls.some(([url]) => url.endsWith("/tree"))).toBe(
    false,
  );
  expect(screen.queryByRole("progressbar")).toBeNull();
  await user.click(screen.getByText("Agent call tree"));
  const totals = await screen.findByText(/Total call-tree tokens: 420/);
  expect(totals).toHaveTextContent("Total cost: $0.025000");
  expect(totals).toHaveTextContent("Tool calls: 3 · 30 ms");
  expect(screen.getByText("inspector")).toBeVisible();
  expect(screen.getByText("Model calls: 2")).toBeVisible();
  expect(screen.getByText("Failed tools: 1")).toBeVisible();
  const usage = screen.getByRole("group", { name: "Budget utilization" });
  expect(usage).toHaveTextContent("Token budget used: 420 / 1,000 · 42%");
  expect(usage).toHaveTextContent(
    "Cost budget used: $0.025000 / $0.100000 · 25%",
  );
  expect(fetchMock.mock.calls.filter(([url]) => url.endsWith("/tree"))).toEqual(
    [
      [
        "/api/agent/conversations/conv-1/tree",
        expect.objectContaining({ method: "GET" }),
      ],
    ],
  );
});
