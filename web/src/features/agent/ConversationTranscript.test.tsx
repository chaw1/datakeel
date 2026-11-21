import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";
import {
  agentEvent,
  conversation,
  completedPlanEvent,
  planEvent,
  toolEvent,
} from "../../test/agentFixtures";

import { ConversationTranscript } from "./ConversationTranscript";

import type { AgentEvent } from "../../api/types";

it("renders user turns, folded tools, text and stopped events in sequence", async () => {
  const user = userEvent.setup();
  render(
    <ConversationTranscript
      conversation={{
        ...conversation,
        messages: [
          { role: "user", content: "Find low quality files", tool_calls: [] },
        ],
        events: [
          toolEvent,
          agentEvent("text", { text: "Found matching files" }),
          agentEvent("stopped", { stop_reason: "budget_exceeded" }),
          agentEvent("done"),
        ],
      }}
      live={{ content: "", events: [] }}
      busy={false}
      onResolved={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByText("Find low quality files")).toBeVisible();
  expect(screen.getByText("Found matching files")).toBeVisible();
  expect(screen.getByText("The configured budget was reached.")).toBeVisible();
  const args = screen.getByText(/"quality_max": 60/);
  expect(args).not.toBeVisible();
  await user.click(screen.getByText(/Tool call/));
  expect(args).toBeVisible();
});
it("keeps all plan execution controls unavailable in dry-run conversations", () => {
  render(
    <ConversationTranscript
      conversation={{
        ...conversation,
        config: { ...conversation.config, dry_run: true },
        events: [planEvent, agentEvent("done")],
      }}
      live={{ content: "", events: [] }}
      busy={false}
      onResolved={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(
    screen.getByText("Dry run: this conversation only prepares plans."),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Approve and delete files" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Execute action" }),
  ).not.toBeInTheDocument();
});

it("shows a hydrated automatic receipt once across plan and receipt events", () => {
  render(
    <ConversationTranscript
      conversation={{
        ...conversation,
        events: [
          completedPlanEvent,
          { ...completedPlanEvent, id: "receipt-event", event: "receipt" },
          agentEvent("done"),
        ],
      }}
      live={{ content: "", events: [] }}
      busy={false}
      onResolved={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(
    screen.getAllByRole("link", { name: "View lineage receipt" }),
  ).toHaveLength(1);
});

const pausedEvents = (status: typeof actionPlan.status): AgentEvent[] => [
  {
    ...planEvent,
    outcome: {
      name: "delete_files",
      status: "SUCCEEDED",
      requires_approval: true,
      plan: { ...actionPlan, status },
    },
  },
  agentEvent("done", { id: "child-done", agent_path: "main/specialist#1" }),
  agentEvent("stopped", { stop_reason: "approval_required" }),
  agentEvent("done"),
];
const transcriptProps = {
  busy: false,
  live: { content: "", events: [] as AgentEvent[] },
  onResolved: vi.fn(),
  onOpenReceipt: vi.fn(),
};

it.each(["APPROVED", "EXECUTED"] as const)(
  "resumes the latest %s approval pause using its plan id",
  async (status) => {
    const onResume = vi.fn();
    render(
      <ConversationTranscript
        {...transcriptProps}
        conversation={{ ...conversation, events: pausedEvents(status) }}
        onResume={onResume}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Continue conversation" }),
    );
    expect(onResume).toHaveBeenCalledWith(actionPlan.id);
  },
);

it.each([
  { busy: true, dryRun: false },
  { busy: false, dryRun: true },
])("disables approval continuation with %o", ({ busy, dryRun }) => {
  render(
    <ConversationTranscript
      {...transcriptProps}
      busy={busy}
      conversation={{
        ...conversation,
        config: { ...conversation.config, dry_run: dryRun },
        events: pausedEvents("APPROVED"),
      }}
      onResume={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Continue conversation" }),
  ).toBeDisabled();
});

it("does not offer continuation before approval or after a newer turn", () => {
  const props = { ...transcriptProps, onResume: vi.fn() };
  const { rerender } = render(
    <ConversationTranscript
      {...props}
      conversation={{ ...conversation, events: pausedEvents("PREPARED") }}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "Continue conversation" }),
  ).toBeNull();
  rerender(
    <ConversationTranscript
      {...props}
      conversation={{
        ...conversation,
        events: [
          ...pausedEvents("APPROVED"),
          agentEvent("text", { id: "next-text", text: "A fresh answer" }),
          agentEvent("stopped", {
            id: "next-stop",
            stop_reason: "approval_required",
          }),
          agentEvent("done", { id: "next-done" }),
        ],
      }}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "Continue conversation" }),
  ).toBeNull();
  rerender(
    <ConversationTranscript
      {...props}
      conversation={{ ...conversation, events: pausedEvents("APPROVED") }}
      live={{ content: "Start something new", events: [] }}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "Continue conversation" }),
  ).toBeNull();
});

it("forwards an unsupported request through the transcript escalation button", async () => {
  const onEscalateAgent = vi.fn();
  render(
    <ConversationTranscript
      {...transcriptProps}
      onEscalateAgent={onEscalateAgent}
      conversation={{
        ...conversation,
        events: [
          agentEvent("intent", {
            intent: {
              kind: "unsupported",
              parser: "rules",
              request: "Explore relationships",
              text: "Try the deep agent",
            },
          }),
        ],
      }}
    />,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Ask Deep Agent instead" }),
  );
  expect(onEscalateAgent).toHaveBeenCalledWith("Explore relationships");
});

it("keeps resumed receipts with the original user turn and later messages with their answer", () => {
  const { container } = render(
    <ConversationTranscript
      {...transcriptProps}
      onResume={vi.fn()}
      conversation={{
        ...conversation,
        messages: [
          { role: "user", content: "Delete these files", tool_calls: [] },
          { role: "user", content: "Show remaining files", tool_calls: [] },
        ],
        events: [
          ...pausedEvents("EXECUTED"),
          agentEvent("receipt", {
            outcome: {
              name: "execute_plan",
              status: "SUCCEEDED",
              requires_approval: false,
              run: actionRun,
            },
          }),
          agentEvent("text", {
            id: "resumed-text",
            text: "Deletion completed",
          }),
          agentEvent("done", { id: "resumed-done" }),
          agentEvent("text", {
            id: "latest-text",
            text: "Here are remaining files",
          }),
          agentEvent("done", { id: "latest-done" }),
        ],
      }}
    />,
  );
  expect(container.querySelectorAll(".user-message")).toHaveLength(2);
  expect(
    screen.getByText("Deletion completed").closest(".conversation-turn"),
  ).toBe(screen.getByText("Delete these files").closest(".conversation-turn"));
  expect(
    screen.getByText("Here are remaining files").closest(".conversation-turn"),
  ).toBe(
    screen.getByText("Show remaining files").closest(".conversation-turn"),
  );
  expect(
    screen.queryByRole("button", { name: "Continue conversation" }),
  ).toBeNull();
});
