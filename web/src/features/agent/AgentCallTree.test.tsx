import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { AgentCallTree } from "./AgentCallTree";

import type { CallTree } from "../../api/types";

const tree: CallTree = {
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

afterEach(() => vi.unstubAllGlobals());

it("loads root and specialist usage only when expanded and stays idle while collapsed", async () => {
  const fetch = vi.fn(() => Promise.resolve(Response.json(tree)));
  vi.stubGlobal("fetch", fetch);
  const { rerender } = render(<AgentCallTree conversationId="root" />);
  expect(fetch).not.toHaveBeenCalled();
  await userEvent.click(screen.getByText("Agent call tree"));
  expect(await screen.findByText("Total call-tree tokens: 100")).toBeVisible();
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
  expect(await screen.findByText("Total call-tree tokens: 100")).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(2);
});
