import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import {
  agentEvent,
  conversation,
  completedPlanEvent,
  planEvent,
  toolEvent,
} from "../../test/agentFixtures";

import { ConversationTranscript } from "./ConversationTranscript";

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
