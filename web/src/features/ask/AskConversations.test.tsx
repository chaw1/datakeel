import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AskConversations } from "./AskConversations";

import type { AskConversation } from "../../api/ask";

const conversation: AskConversation = {
  id: "thread-1",
  actor: "reader",
  title: "Regional revenue",
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
  turns: [],
  current_frame: null,
};

it("lists, opens, deletes saved conversations through actor-scoped endpoints", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify([conversation])))
    .mockResolvedValueOnce(new Response(JSON.stringify(conversation)))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const onOpen = vi.fn();
  const onDeleted = vi.fn();
  const onNew = vi.fn();
  render(
    <AskConversations
      actor="reader"
      activeId="thread-1"
      disabled={false}
      onOpen={onOpen}
      onDeleted={onDeleted}
      onNew={onNew}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Saved conversations" }));
  await user.click(
    await screen.findByRole("button", {
      name: "Open conversation: Regional revenue",
    }),
  );
  expect(onOpen).toHaveBeenCalledWith(conversation);
  expect(fetch.mock.calls[1]?.[0]).toBe("/api/ask/conversations/thread-1");
  const headers = fetch.mock.calls[1]?.[1] as RequestInit;
  expect(new Headers(headers.headers).get("X-Datakeel-Actor")).toBe("reader");
  await user.click(
    screen.getByRole("button", {
      name: "Delete conversation: Regional revenue",
    }),
  );
  await waitFor(() => {
    expect(onDeleted).toHaveBeenCalledWith("thread-1");
  });
  expect(screen.getByText("No saved conversations yet.")).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith("/api/ask/conversations/thread-1", {
    method: "DELETE",
    headers: { "X-Datakeel-Actor": "reader" },
  });
  await user.click(screen.getByRole("button", { name: "New conversation" }));
  expect(onNew).toHaveBeenCalledOnce();
});

it("shows a failed deletion and preserves the saved entry", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify([conversation])))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Access denied" }), {
          status: 403,
        }),
      ),
  );
  const user = userEvent.setup();
  const onDeleted = vi.fn();
  render(
    <AskConversations
      actor="reader"
      disabled={false}
      onOpen={vi.fn()}
      onDeleted={onDeleted}
      onNew={vi.fn()}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Saved conversations" }));
  await user.click(
    await screen.findByRole("button", {
      name: "Delete conversation: Regional revenue",
    }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "403 Access denied",
  );
  expect(
    screen.getByRole("button", { name: "Open conversation: Regional revenue" }),
  ).toBeVisible();
  expect(onDeleted).not.toHaveBeenCalled();
});
