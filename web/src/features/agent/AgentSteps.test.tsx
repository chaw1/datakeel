import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { agentEvent, conversation } from "../../test/agentFixtures";

import { ConversationTranscript } from "./ConversationTranscript";

it("nests delegated steps, tools and token usage without creating another user turn", async () => {
  const path = "main/catalog-analyst#1";
  const events = [
    agentEvent("tool_call", {
      id: "child-call",
      agent_path: path,
      agent_name: "catalog-analyst",
      call: { id: "catalog-call", name: "catalog_search", arguments: {} },
    }),
    agentEvent("text", {
      id: "child-text",
      agent_path: path,
      agent_name: "catalog-analyst",
      text: "Catalog reviewed",
    }),
    agentEvent("text", {
      id: "nested-text",
      agent_path: `${path}/metric-manager#1`,
      agent_name: "metric-manager",
      text: "Metric reviewed",
    }),
    agentEvent("done", {
      id: "nested-done",
      agent_path: `${path}/metric-manager#1`,
      tokens: 50,
    }),
    agentEvent("done", { id: "child-done", agent_path: path, tokens: 150 }),
    agentEvent("text", { text: "Root response" }),
    agentEvent("done"),
  ];
  const { container } = render(
    <ConversationTranscript
      conversation={{
        ...conversation,
        messages: [
          {
            role: "user",
            content: "Delegate catalog analysis",
            tool_calls: [],
          },
        ],
        events,
      }}
      live={{ content: "", events: [] }}
      busy={false}
      onResolved={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByText("Catalog reviewed")).not.toBeVisible();
  expect(screen.getByText("200 tokens")).toBeVisible();
  await userEvent.click(screen.getByText("catalog-analyst"));
  expect(screen.getByText("Catalog reviewed")).toBeVisible();
  expect(screen.getByText("Metric reviewed")).not.toBeVisible();
  await userEvent.click(screen.getByText("metric-manager"));
  expect(screen.getByText("Metric reviewed")).toBeVisible();
  expect(container.querySelectorAll(".user-message")).toHaveLength(1);
  expect(screen.getByText("Root response")).toBeVisible();
  expect(screen.getByText("Root response").closest(".conversation-turn")).toBe(
    screen.getByText("Delegate catalog analysis").closest(".conversation-turn"),
  );
  expect(
    container.querySelector(".delegation-step .delegation-step"),
  ).toBeInTheDocument();
});
