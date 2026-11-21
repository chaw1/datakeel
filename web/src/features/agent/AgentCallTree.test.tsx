import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { AgentCallTree } from "./AgentCallTree";

import type { CallTree, ConversationCreate } from "../../api/types";

const tree = {
  nodes: [
    {
      id: "root",
      root_id: "root",
      parent_id: null,
      parent_tool_call_id: null,
      agent_name: "main",
      agent_path: "main",
      depth: 0,
      tokens: 30,
      tools: ["delegate_agent"],
    },
    {
      id: "child",
      root_id: "root",
      parent_id: "root",
      parent_tool_call_id: "call-1",
      agent_name: "inspector",
      agent_path: "main/inspector",
      depth: 1,
      tokens: 70,
      tools: ["search_files"],
    },
  ],
  traces: [],
};
const budget: ConversationCreate["budget"] = {
  conversation_tokens: 1000,
  conversation_usd: "0.1",
  daily_tokens: 10000,
  daily_usd: "1",
};
const budgetWarning = "At least 80% of the conversation budget is used.";

afterEach(() => vi.unstubAllGlobals());

it("loads root and specialist usage only when expanded and stays idle while collapsed", async () => {
  const fetch = vi.fn(() => Promise.resolve(Response.json(tree)));
  vi.stubGlobal("fetch", fetch);
  const { rerender } = render(<AgentCallTree conversationId="root" />);
  expect(fetch).not.toHaveBeenCalled();
  await userEvent.click(screen.getByText("Agent call tree"));
  const summary = await screen.findByText(/Total call-tree tokens: 100/);
  expect(summary).toHaveTextContent("Total cost: $0.000000");
  expect(summary).toHaveTextContent("Tool calls: 0 · 0 ms");
  expect(screen.queryByText(/Models:/)).toBeNull();
  expect(screen.queryByText(/Failed tools:/)).toBeNull();
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(screen.getByText("main/inspector")).toBeVisible();
  expect(screen.getByText("inspector")).toBeVisible();
  expect(screen.getByText(/delegate_agent/)).toBeVisible();
  expect(screen.getByText(/search_files/)).toBeVisible();
  expect(fetch).toHaveBeenCalledExactlyOnceWith(
    "/api/agent/conversations/root/tree",
    expect.objectContaining({ method: "GET" }),
  );
  await userEvent.click(screen.getByText("Agent call tree"));
  await waitFor(() => {
    expect(screen.queryByText("inspector")).toBeNull();
  });
  rerender(<AgentCallTree conversationId="root" revision={1} />);
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("shows accurate budget meters only after expansion and hides them on collapse", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(
      Response.json({ ...tree, total_tokens: 420, total_cost_usd: "0.025" }),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(<AgentCallTree conversationId="root" budget={budget} />);
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
  await userEvent.click(screen.getByText("Agent call tree"));
  const meters = await screen.findByRole("group", {
    name: "Budget utilization",
  });
  const tokenMeter = within(meters).getByRole("progressbar", {
    name: "Token budget used",
  });
  expect(tokenMeter).toHaveAttribute("value", "420");
  expect(tokenMeter).toHaveAttribute("max", "1000");
  expect(meters).toHaveTextContent("Token budget used: 420 / 1,000 · 42%");
  const costMeter = within(meters).getByRole("progressbar", {
    name: "Cost budget used",
  });
  expect(costMeter).toHaveAttribute("value", "0.025");
  expect(costMeter).toHaveAttribute("max", "0.1");
  expect(meters).toHaveTextContent(
    "Cost budget used: $0.025000 / $0.100000 · 25%",
  );
  expect(screen.queryByText(budgetWarning)).toBeNull();
  await userEvent.click(screen.getByText("Agent call tree"));
  await waitFor(() => {
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
  expect(fetch).toHaveBeenCalledTimes(1);
});

it.each([
  { tokens: 800, cost: "0.02", warning: true },
  { tokens: 100, cost: "0.08", warning: true },
  { tokens: 799, cost: "0.0799", warning: false },
])(
  "warns at 80% of either budget: $tokens tokens, $cost USD",
  async ({ tokens, cost, warning }) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          Response.json({
            ...tree,
            total_tokens: tokens,
            total_cost_usd: cost,
          }),
        ),
      ),
    );
    render(<AgentCallTree conversationId="root" budget={budget} />);
    await userEvent.click(screen.getByText("Agent call tree"));
    await screen.findByRole("group", { name: "Budget utilization" });
    if (warning) {
      expect(screen.getByText(budgetWarning)).toHaveClass("ui-badge-warn");
    } else {
      expect(screen.queryByText(budgetWarning)).toBeNull();
    }
  },
);

it.each([
  { tokens: 0, cost: "0", ratio: 0 },
  { tokens: 1, cost: "0.001", ratio: 1 },
])(
  "keeps zero-limit meters consistent with $tokens tokens and $cost USD",
  async ({ tokens, cost, ratio }) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          Response.json({
            ...tree,
            total_tokens: tokens,
            total_cost_usd: cost,
          }),
        ),
      ),
    );
    render(
      <AgentCallTree
        conversationId="root"
        budget={{ ...budget, conversation_tokens: 0, conversation_usd: "0" }}
      />,
    );
    await userEvent.click(screen.getByText("Agent call tree"));
    const usage = await screen.findByRole("group", {
      name: "Budget utilization",
    });
    for (const meter of within(usage).getAllByRole("progressbar")) {
      expect(meter).toHaveProperty("max", 1);
      expect(meter).toHaveProperty("value", ratio);
      expect(meter.parentElement).toHaveTextContent(`${String(ratio * 100)}%`);
    }
    expect(usage).toHaveTextContent("/ $0.000000");
    expect(screen.queryByText(budgetWarning) !== null).toBe(ratio > 0);
  },
);

it("shows a failed request and retries without opening a new conversation", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json({ detail: "Tree unavailable" }, { status: 503 }),
    )
    .mockResolvedValueOnce(Response.json(tree));
  vi.stubGlobal("fetch", fetch);
  render(<AgentCallTree conversationId="root" />);
  await userEvent.click(screen.getByText("Agent call tree"));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Tree unavailable",
  );
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText(/Total call-tree tokens: 100/)).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("shows session totals, distinct models and each specialist's cost and latency", async () => {
  const measured: CallTree = {
    ...tree,
    total_tokens: 125,
    total_cost_usd: "0.0125",
    total_tool_calls: 3,
    total_tool_elapsed_ms: 40.75,
    models: ["fake/planner", "fake/inspector"],
    nodes: tree.nodes.map((node) => ({
      ...node,
      cost_usd: node.depth ? "0.01" : "0.0025",
      model_calls: node.depth ? 2 : 1,
      tool_elapsed_ms: node.depth ? 30.5 : 10.25,
      failed_tools: node.depth ? 1 : 0,
    })),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(Response.json(measured))),
  );
  render(<AgentCallTree conversationId="root" />);
  await userEvent.click(screen.getByText("Agent call tree"));
  const summary = await screen.findByText(/Total call-tree tokens: 125/);
  expect(summary).toHaveTextContent("Total cost: $0.012500");
  expect(summary).toHaveTextContent("Tool calls: 3 · 41 ms");
  expect(
    screen.getByText("Models: fake/planner, fake/inspector"),
  ).toBeVisible();
  const [root, child] = screen.getAllByRole("listitem");
  expect(within(root).getByText("$0.002500")).toBeVisible();
  expect(within(root).getByText("Model calls: 1")).toBeVisible();
  expect(within(root).getByText("Tool latency: 10 ms")).toBeVisible();
  expect(within(root).queryByText(/Failed tools:/)).toBeNull();
  expect(within(child).getByText("$0.010000")).toBeVisible();
  expect(within(child).getByText("Model calls: 2")).toBeVisible();
  expect(within(child).getByText("Tool latency: 31 ms")).toBeVisible();
  expect(within(child).getByText("Failed tools: 1")).toHaveClass(
    "ui-badge-warn",
  );
});
