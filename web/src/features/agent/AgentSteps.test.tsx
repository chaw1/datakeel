import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { parseAgentEvent } from "../../api/agent";
import { agentEvent, conversation } from "../../test/agentFixtures";

import { ConversationTranscript } from "./ConversationTranscript";

import type { AgentEvent } from "../../api/types";

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

it("shows Running only for unmatched live calls on the same agent path", async () => {
  const rootCall = agentEvent("tool_call", {
    id: "root-call",
    call: { id: "root-tool", name: "delegate_to_agent", arguments: {} },
  });
  const childCall = agentEvent("tool_call", {
    id: "child-call",
    agent_path: "main/reviewer#1",
    agent_name: "reviewer",
    call: { id: "child-tool", name: "catalog_search", arguments: {} },
  });
  const props = {
    busy: true,
    conversation: {
      ...conversation,
      events: [
        agentEvent("tool_call", { id: "old-call", call: rootCall.call }),
      ],
    },
    onResolved: vi.fn(),
    onOpenReceipt: vi.fn(),
  };
  const events = [rootCall, childCall];
  const { rerender } = render(
    <ConversationTranscript {...props} live={{ content: "Review", events }} />,
  );
  await userEvent.click(screen.getByText("reviewer"));
  expect(screen.getAllByText("Running")).toHaveLength(2);
  events.push(
    agentEvent("tool_result", {
      agent_path: childCall.agent_path,
      outcome: {
        name: "catalog_search",
        status: "SUCCEEDED",
        requires_approval: false,
      },
    }),
  );
  rerender(
    <ConversationTranscript {...props} live={{ content: "Review", events }} />,
  );
  expect(screen.getAllByText("Running")).toHaveLength(1);
  expect(screen.getByText("Running").closest("summary")).toHaveTextContent(
    "delegate_to_agent",
  );
  events.push(agentEvent("tool_result", { id: "root-result" }));
  rerender(
    <ConversationTranscript {...props} live={{ content: "Review", events }} />,
  );
  expect(screen.queryByText("Running")).not.toBeInTheDocument();
});

it("matches explicit result call ids and clears pending badges at a path's stop", () => {
  const first = agentEvent("tool_call", {
    id: "first-call",
    call: { id: "tool-1", name: "first_tool", arguments: {} },
  });
  const second = agentEvent("tool_call", {
    id: "second-call",
    call: { id: "tool-2", name: "second_tool", arguments: {} },
  });
  const props = {
    busy: true,
    conversation,
    onResolved: vi.fn(),
    onOpenReceipt: vi.fn(),
  };
  const events: AgentEvent[] = [
    first,
    second,
    agentEvent("tool_result", { call: second.call }),
  ];
  const { rerender } = render(
    <ConversationTranscript {...props} live={{ content: "Run", events }} />,
  );
  expect(screen.getByText("Running").closest("summary")).toHaveTextContent(
    "first_tool",
  );
  rerender(
    <ConversationTranscript
      {...props}
      live={{
        content: "Run",
        events: [
          ...events,
          agentEvent("stopped", { stop_reason: "canary_leak" }),
        ],
      }}
    />,
  );
  expect(screen.queryByText("Running")).not.toBeInTheDocument();
  rerender(
    <ConversationTranscript
      {...props}
      busy={false}
      live={{ content: "Run", events }}
    />,
  );
  expect(screen.queryByText("Running")).not.toBeInTheDocument();
});

it("renders legacy events without delegation fields on the main path", () => {
  render(
    <ConversationTranscript
      conversation={{
        ...conversation,
        events: [
          parseAgentEvent(
            '{"event":"text","id":"legacy","text":"Legacy response","tokens":0}',
          ),
        ],
      }}
      live={{ content: "", events: [] }}
      busy={false}
      onResolved={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByText("Legacy response")).toBeVisible();
});
