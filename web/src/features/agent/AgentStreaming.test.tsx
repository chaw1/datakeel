import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AgentPage } from "../../pages/AgentPage";
import { agentEvent, conversation } from "../../test/agentFixtures";
import { dataset } from "../../test/fixtures";

it("renders an arriving SSE chunk while the stream is still open", async () => {
  const user = userEvent.setup();
  const text = agentEvent("text", { text: "Live result before completion" });
  const done = agentEvent("done");
  let writer: ReadableStreamDefaultController<Uint8Array> | undefined;
  let sent = false;
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
            events: [text, done],
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
  await user.type(
    await screen.findByRole("textbox", { name: "Message" }),
    "Inspect low quality files",
  );
  await user.click(screen.getByRole("button", { name: "Send message" }));
  await act(async () => {
    writer?.enqueue(
      new TextEncoder().encode(
        `event: text\ndata: ${JSON.stringify(text)}\n\n`,
      ),
    );
    await Promise.resolve();
  });
  expect(
    await screen.findByText("Live result before completion"),
  ).toBeVisible();
  expect(screen.getByRole("textbox", { name: "Message" })).toBeDisabled();
  await act(async () => {
    writer?.enqueue(
      new TextEncoder().encode(
        `event: done\ndata: ${JSON.stringify(done)}\n\n`,
      ),
    );
    writer?.close();
    await Promise.resolve();
  });
  await waitFor(() => {
    expect(screen.getByRole("textbox", { name: "Message" })).toBeEnabled();
  });
  expect(screen.getAllByText("Live result before completion")).toHaveLength(1);
});
