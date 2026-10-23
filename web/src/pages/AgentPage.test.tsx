import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../test/actionFixtures";
import {
  agentEvent,
  conversation,
  completedPlanEvent,
  eventStream,
  planEvent,
  toolEvent,
} from "../test/agentFixtures";
import { dataset } from "../test/fixtures";

import { AgentPage } from "./AgentPage";

import type { Conversation } from "../api/types";

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
  return new Response(JSON.stringify(value));
}

it("renders a POST SSE turn and reloads the saved transcript without duplicating it", async () => {
  const user = userEvent.setup();
  let sent = false;
  const events = [
    toolEvent,
    agentEvent("text", { text: "Matching files are ready." }),
    agentEvent("done"),
  ];
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    if (path.endsWith("/messages") && init?.method === "POST") {
      sent = true;
      return Promise.resolve(eventStream(events));
    }
    const current = sent ? withMessage(events) : conversation;
    return Promise.resolve(
      json(path === "/api/agent/conversations" ? [current] : current),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<AgentPage {...props} />);
  await user.type(
    await screen.findByRole("textbox", { name: "Message" }),
    "Inspect low quality files",
  );
  await user.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => {
    expect(screen.getByRole("textbox", { name: "Message" })).toBeEnabled();
  });
  expect(screen.getAllByText("Matching files are ready.")).toHaveLength(1);
  expect(
    screen.getByRole("region", { name: "Conversation activity" }),
  ).toHaveTextContent("Inspect low quality files");
  const message = fetch.mock.calls.find(([path]) => path.endsWith("/messages"));
  expect(message?.[1]?.method).toBe("POST");
  const body = message?.[1]?.body;
  if (typeof body !== "string") throw new Error("Missing message body");
  expect(body).toContain('"content":"Inspect low quality files"');
  expect(body).toMatch(/"idempotency_key":"[\w-]+"/);
});

it("restores persisted messages after a dropped stream without repeating the POST", async () => {
  const user = userEvent.setup();
  let sent = false;
  const persisted = [
    agentEvent("text", { text: "Saved response" }),
    agentEvent("done"),
  ];
  const fetch = vi.fn((path: string) => {
    if (path.endsWith("/messages")) {
      sent = true;
      return Promise.resolve(
        eventStream([agentEvent("text", { text: "partial" })]),
      );
    }
    const current = sent ? withMessage(persisted) : conversation;
    return Promise.resolve(
      json(path === "/api/agent/conversations" ? [current] : current),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<AgentPage {...props} />);
  await user.type(
    await screen.findByRole("textbox", { name: "Message" }),
    "Inspect low quality files",
  );
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "connection was interrupted",
  );
  expect(screen.getByText("Saved response")).toBeVisible();
  await user.click(
    screen.getByRole("button", { name: "Reload saved conversation" }),
  );
  await waitFor(() => {
    expect(screen.getByRole("textbox", { name: "Message" })).toBeEnabled();
  });
  expect(
    fetch.mock.calls.filter(([path]) => path.endsWith("/messages")),
  ).toHaveLength(1);
});

it("approves a pending chat plan, executes it, and preserves one linked receipt", async () => {
  const user = userEvent.setup();
  let executed = false;
  const fetch = vi.fn((path: string) => {
    if (path === "/api/approvals/plan-1")
      return Promise.resolve(json({ ...actionPlan, status: "APPROVED" }));
    if (path === "/api/actions/plan-1/execute") {
      executed = true;
      return Promise.resolve(json(actionRun));
    }
    const current = withMessage([
      executed ? completedPlanEvent : planEvent,
      agentEvent("done"),
    ]);
    return Promise.resolve(
      json(path === "/api/agent/conversations" ? [current] : current),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<AgentPage {...props} />);
  await user.click(
    await screen.findByRole("button", { name: "Approve and delete files" }),
  );
  await waitFor(() => {
    expect(
      screen.queryByRole("button", { name: "Approve and delete files" }),
    ).not.toBeInTheDocument();
  });
  expect(
    await screen.findAllByRole("link", { name: "View lineage receipt" }),
  ).toHaveLength(1);
  expect(
    fetch.mock.calls
      .map(([path]) => path)
      .filter(
        (path) =>
          path.includes("/api/actions/") || path.includes("/api/approvals/"),
      ),
  ).toEqual(["/api/approvals/plan-1", "/api/actions/plan-1/execute"]);
});

it("refreshes a stale approval after a conflict without executing or reapproving it", async () => {
  const user = userEvent.setup();
  let conflicted = false;
  const fetch = vi.fn((path: string) => {
    if (path === "/api/approvals/plan-1") {
      conflicted = true;
      return Promise.resolve(
        new Response(
          JSON.stringify({ detail: "Plan was rejected elsewhere" }),
          { status: 409 },
        ),
      );
    }
    const current = withMessage([
      conflicted
        ? {
            ...planEvent,
            outcome: {
              ...completedPlanEvent.outcome,
              name: "delete_files",
              status: "SUCCEEDED",
              plan: { ...actionPlan, status: "REJECTED" },
              requires_approval: false,
              run: null,
            },
          }
        : planEvent,
      agentEvent("done"),
    ]);
    return Promise.resolve(
      json(path === "/api/agent/conversations" ? [current] : current),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<AgentPage {...props} />);
  await user.click(
    await screen.findByRole("button", { name: "Approve and delete files" }),
  );
  await waitFor(() => {
    expect(
      screen.queryByRole("button", { name: "Approve and delete files" }),
    ).not.toBeInTheDocument();
  });
  expect(screen.getByText("Approval sheet · Rejected")).toBeVisible();
  expect(
    fetch.mock.calls.filter(([path]) => path.endsWith("/execute")),
  ).toHaveLength(0);
});

it("creates a dry-run conversation with the user's explicit budget", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn((path: string, init?: RequestInit) =>
    Promise.resolve(
      json(
        path === "/api/agent/conversations" && init?.method !== "POST"
          ? [conversation]
          : conversation,
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(<AgentPage {...props} />);
  await screen.findByRole("textbox", { name: "Message" });
  await user.click(
    screen.getAllByText("Conversation budget", { exact: true })[0],
  );
  const limit = screen.getByRole("spinbutton", {
    name: "Conversation token limit",
  });
  await user.tripleClick(limit);
  await user.keyboard("1000000");
  await user.click(screen.getByRole("checkbox", { name: "Dry run" }));
  await user.click(screen.getByRole("button", { name: "New conversation" }));
  await waitFor(() => {
    expect(
      fetch.mock.calls.some(
        ([path, init]) =>
          path === "/api/agent/conversations" && init?.method === "POST",
      ),
    ).toBe(true);
  });
  const body = fetch.mock.calls.find(([, init]) => init?.method === "POST")?.[1]
    ?.body;
  expect(body).toContain('"conversation_tokens":1000000');
  expect(body).toContain('"dry_run":true');
  expect(body).toContain('"provider":"fake"');
});
