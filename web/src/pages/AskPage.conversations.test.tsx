import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { retailAnswer } from "../features/ask/testFixtures";

import { AskPage } from "./AskPage";

import type { AskConversation } from "../api/ask";

const conversationKey = "datakeel.ask.conversation";
const first = { ...retailAnswer, conversation_id: "thread-1" };
const conversation: AskConversation = {
  id: "thread-1",
  actor: "local-user",
  title: first.question,
  created_at: first.reference_instant,
  updated_at: first.reference_instant,
  turns: [first],
  current_frame: null,
};

afterEach(() => {
  sessionStorage.clear();
});

it("sends the conversation on follow-ups, shows full interpretations, and clears it for a new topic", async () => {
  const next = {
    ...first,
    id: "answer-2",
    question: "What about South China?",
    interpreted_question: "查询零售额,筛选零售区域为华南。",
    interpreted_question_en: "Last quarter retail revenue for South China",
  };
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(first)))
    .mockResolvedValueOnce(new Response(JSON.stringify(next)))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ ...first, conversation_id: "thread-2" })),
    );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  const question = screen.getByRole("textbox", { name: "Business question" });
  await user.type(question, first.question);
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  await screen.findByLabelText("Calculated result");
  expect(sessionStorage.getItem(conversationKey)).toBe("thread-1");
  await user.clear(question);
  await user.type(question, next.question);
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  expect(
    (
      await screen.findAllByText(
        `Understood as: ${next.interpreted_question_en}`,
      )
    ).length,
  ).toBeGreaterThan(0);
  expect(
    screen.queryByText(`Understood as: ${next.interpreted_question}`),
  ).not.toBeInTheDocument();
  const followup = fetch.mock.calls[1]?.[1] as RequestInit;
  expect(JSON.parse(followup.body as string) as object).toMatchObject({
    conversation_id: "thread-1",
    question: next.question,
  });
  await user.click(screen.getByRole("button", { name: "New conversation" }));
  expect(sessionStorage.getItem(conversationKey)).toBeNull();
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  await screen.findByLabelText("Calculated result");
  const fresh = fetch.mock.calls[2]?.[1] as RequestInit;
  expect(JSON.parse(fresh.body as string) as object).not.toHaveProperty(
    "conversation_id",
  );
});

it("restores the active thread after a remount and deletes its local selection", async () => {
  sessionStorage.setItem(conversationKey, "thread-1");
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(conversation)))
    .mockResolvedValueOnce(new Response(JSON.stringify([conversation])))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  expect(await screen.findByLabelText("Calculated result")).toHaveTextContent(
    "4,979,475",
  );
  expect(fetch.mock.calls[0]?.[0]).toBe("/api/ask/conversations/thread-1");
  await user.click(screen.getByRole("button", { name: "Saved conversations" }));
  await user.click(
    await screen.findByRole("button", {
      name: `Delete conversation: ${first.question}`,
    }),
  );
  await waitFor(() => {
    expect(sessionStorage.getItem(conversationKey)).toBeNull();
  });
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
});

it("clears an inaccessible restored thread and exposes the API refusal", async () => {
  sessionStorage.setItem(conversationKey, "deleted-thread");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Conversation not found" }), {
        status: 404,
      }),
    ),
  );
  render(<AskPage onOpenReceipt={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "404 Conversation not found",
  );
  expect(sessionStorage.getItem(conversationKey)).toBeNull();
  expect(
    screen.getByRole("textbox", { name: "Business question" }),
  ).toBeEnabled();
});
