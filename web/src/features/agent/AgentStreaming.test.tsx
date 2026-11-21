import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AgentPage } from "../../pages/AgentPage";
import { agentEvent, conversation } from "../../test/agentFixtures";
import { dataset } from "../../test/fixtures";

import type { AgentEvent } from "../../api/types";

async function openStream() {
  let writer!: ReadableStreamDefaultController<Uint8Array>;
  let sent = false;
  const saved: AgentEvent[] = [];
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      writer = controller;
    },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) => {
      if (path.endsWith("/messages")) {
        sent = true;
        return Promise.resolve(
          new Response(stream, {
            headers: { "Content-Type": "text/event-stream" },
          }),
        );
      }
      const current = sent
        ? {
            ...conversation,
            events: saved,
            messages: [{ role: "user", content: "Inspect low quality files" }],
          }
        : conversation;
      return Promise.resolve(
        new Response(
          JSON.stringify(
            path === "/api/agent/conversations" ? [current] : current,
          ),
        ),
      );
    }),
  );
  render(
    <AgentPage
      datasets={[dataset]}
      datasetId={dataset.id}
      conversationId={conversation.id}
      onConversation={vi.fn()}
      onDataChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
      onTrace={vi.fn()}
    />,
  );
  const user = userEvent.setup();
  await user.type(
    await screen.findByRole("textbox", { name: "Message" }),
    "Inspect low quality files",
  );
  await user.click(screen.getByRole("button", { name: "Send message" }));
  return {
    async push(event: AgentEvent) {
      if (event.event !== "text_delta") saved.push(event);
      await act(async () => {
        writer.enqueue(
          new TextEncoder().encode(
            `event: ${event.event}\ndata: ${JSON.stringify(event)}\n\n`,
          ),
        );
        await Promise.resolve();
      });
    },
    async close() {
      await act(async () => {
        writer.close();
        await Promise.resolve();
      });
      await waitFor(() => {
        expect(screen.getByRole("textbox", { name: "Message" })).toBeEnabled();
      });
    },
  };
}

it("renders incremental deltas while open and replaces them with committed text once", async () => {
  const stream = await openStream();
  await stream.push(agentEvent("text_delta", { id: "delta-1", text: "Live " }));
  expect(await screen.findByText("Live")).toBeVisible();
  await stream.push(
    agentEvent("text_delta", {
      id: "delta-2",
      text: "result before completion",
    }),
  );
  expect(
    await screen.findByText("Live result before completion"),
  ).toBeVisible();
  expect(screen.queryByText("Live")).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Message" })).toBeDisabled();
  await stream.push(
    agentEvent("text", { text: "Live result before completion." }),
  );
  expect(
    screen.queryByText("Live result before completion"),
  ).not.toBeInTheDocument();
  expect(screen.getAllByText("Live result before completion.")).toHaveLength(1);
  await stream.push(agentEvent("done"));
  await stream.close();
  expect(screen.getAllByText("Live result before completion.")).toHaveLength(1);
});

it("clears a stopped child's preview immediately while preserving the parent's preview", async () => {
  const stream = await openStream();
  const child = { agent_path: "main/reviewer#1", agent_name: "reviewer" };
  await stream.push(
    agentEvent("text_delta", { id: "root-delta", text: "Root preview" }),
  );
  await stream.push(
    agentEvent("text_delta", {
      ...child,
      id: "child-delta",
      text: "Child preview",
    }),
  );
  await userEvent.click(screen.getByText("reviewer"));
  expect(screen.getByText("Child preview")).toBeVisible();
  await stream.push(
    agentEvent("stopped", { ...child, stop_reason: "canary_leak" }),
  );
  expect(screen.queryByText("Child preview")).not.toBeInTheDocument();
  expect(screen.getByText("Root preview")).toBeVisible();
  expect(screen.getByText(/protected session marker/)).toBeVisible();
  await stream.push(agentEvent("done", { ...child, id: "child-done" }));
  expect(screen.getByText("Root preview")).toBeVisible();
  await stream.push(agentEvent("done"));
  expect(screen.queryByText("Root preview")).not.toBeInTheDocument();
  await stream.close();
});

it("discards a failed attempt's preview before rendering fallback text", async () => {
  const stream = await openStream();
  await stream.push(
    agentEvent("text_delta", { id: "primary-delta", text: "Partial primary" }),
  );
  expect(screen.getByText("Partial primary")).toBeVisible();
  await stream.push(agentEvent("text_delta", { id: "null-delta", text: null }));
  expect(screen.getByText("Partial primary")).toBeVisible();
  await stream.push(agentEvent("text_delta", { id: "retry-reset", text: "" }));
  expect(screen.queryByText("Partial primary")).not.toBeInTheDocument();
  await stream.push(
    agentEvent("text_delta", { id: "backup-delta", text: "Backup answer" }),
  );
  expect(screen.getByText("Backup answer")).toBeVisible();
  expect(screen.queryByText(/Partial primary/)).not.toBeInTheDocument();
  await stream.push(agentEvent("text", { text: "Backup answer." }));
  await stream.push(agentEvent("done"));
  await stream.close();
  expect(screen.getAllByText("Backup answer.")).toHaveLength(1);
});
