import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { retailAnswer } from "../features/ask/testFixtures";

import { AskPage } from "./AskPage";

const first = { ...retailAnswer, conversation_id: "thread-1" };
const conversation = {
  id: "thread-1",
  actor: "local-user",
  title: "Saved regional question",
  created_at: first.reference_instant,
  updated_at: first.reference_instant,
  turns: [first],
  current_frame: null,
};

afterEach(() => {
  sessionStorage.clear();
});

it("prevents submit and replay while a delayed conversation open is pending", async () => {
  let complete: ((response: Response) => void) | undefined;
  const next = {
    ...first,
    id: "answer-2",
    result: { columns: ["value"], rows: [[333]], truncated: false },
  };
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(first)))
    .mockResolvedValueOnce(new Response(JSON.stringify([conversation])))
    .mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          complete = resolve;
        }),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify(next)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  await user.type(
    screen.getByRole("textbox", { name: "Business question" }),
    first.question,
  );
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  await screen.findByLabelText("Calculated result");
  await user.click(screen.getByRole("button", { name: "Saved conversations" }));
  await user.click(
    await screen.findByRole("button", {
      name: `Open conversation: ${conversation.title}`,
    }),
  );
  expect(
    screen.getByRole("textbox", { name: "Business question" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("textbox", { name: "Operator identity" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "New conversation" }),
  ).toBeDisabled();
  const submit = screen.getByRole("button", { name: "Ask data" });
  const replay = screen.getByRole("button", { name: "Replay saved answer" });
  expect(submit).toBeDisabled();
  expect(replay).toBeDisabled();
  await user.click(submit);
  await user.click(replay);
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(
    screen.queryByText("Finding records and evidence…"),
  ).not.toBeInTheDocument();
  await act(async () => {
    complete?.(new Response(JSON.stringify(conversation)));
    await Promise.resolve();
  });
  expect(submit).toBeEnabled();
  await user.click(submit);
  expect(await screen.findByLabelText("Calculated result")).toHaveTextContent(
    "333",
  );
  const init = fetch.mock.calls[3]?.[1] as RequestInit;
  expect(JSON.parse(init.body as string) as object).toMatchObject({
    conversation_id: "thread-1",
  });
});

it("removes the previous actor's loaded list when the editable identity changes", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValueOnce(new Response(JSON.stringify([conversation]))),
  );
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: "Saved conversations" }));
  await screen.findByRole("button", {
    name: `Open conversation: ${conversation.title}`,
  });
  const actor = screen.getByRole("textbox", { name: "Operator identity" });
  await user.clear(actor);
  await user.type(actor, "other-reader");
  expect(screen.queryByText(/Saved regional question/)).not.toBeInTheDocument();
});
