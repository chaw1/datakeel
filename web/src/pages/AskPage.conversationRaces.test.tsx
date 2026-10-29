import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { AskConversations } from "../features/ask/AskConversations";
import { retailAnswer } from "../features/ask/testFixtures";
import { I18nProvider } from "../i18n/I18nProvider";
import { useI18n } from "../i18n/useI18n";

import { AskPage } from "./AskPage";

const first = { ...retailAnswer, conversation_id: "thread-1" };
const conversation = {
  id: "thread-1",
  actor: "local-user",
  title: "Private regional question",
  created_at: first.reference_instant,
  updated_at: first.reference_instant,
  turns: [first],
  current_frame: null,
};

afterEach(() => {
  sessionStorage.clear();
});

function LocaleSwitch() {
  const { setLocale, t } = useI18n();
  return (
    <button
      type="button"
      onClick={() => {
        setLocale("zh");
      }}
    >
      {t("askChartTitle")}
    </button>
  );
}

it("clears the old actor's list and ignores an open response that finishes after identity changes", async () => {
  let complete: ((response: Response) => void) | undefined;
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify([conversation])))
    .mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          complete = resolve;
        }),
    );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const callbacks = { onOpen: vi.fn(), onNew: vi.fn(), onDeleted: vi.fn() };
  const { rerender } = render(
    <AskConversations
      key="local-user"
      actor="local-user"
      disabled={false}
      {...callbacks}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Saved conversations" }));
  await user.click(
    await screen.findByRole("button", {
      name: `Open conversation: ${conversation.title}`,
    }),
  );
  rerender(
    <AskConversations
      key="other-reader"
      actor="other-reader"
      disabled={false}
      {...callbacks}
    />,
  );
  expect(
    screen.queryByText(/Private regional question/),
  ).not.toBeInTheDocument();
  await act(async () => {
    complete?.(new Response(JSON.stringify(conversation)));
    await Promise.resolve();
  });
  expect(callbacks.onOpen).not.toHaveBeenCalled();
});

it("ignores an old actor's list response that finishes after identity changes", async () => {
  let complete: ((response: Response) => void) | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          complete = resolve;
        }),
    ),
  );
  const user = userEvent.setup();
  const callbacks = { onOpen: vi.fn(), onNew: vi.fn(), onDeleted: vi.fn() };
  const { rerender } = render(
    <AskConversations
      key="local-user"
      actor="local-user"
      disabled={false}
      {...callbacks}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Saved conversations" }));
  rerender(
    <AskConversations
      key="other-reader"
      actor="other-reader"
      disabled={false}
      {...callbacks}
    />,
  );
  await act(async () => {
    complete?.(new Response(JSON.stringify([conversation])));
    await Promise.resolve();
  });
  expect(
    screen.queryByText(/Private regional question/),
  ).not.toBeInTheDocument();
});

it("restores once and keeps the new thread when the language changes", async () => {
  sessionStorage.setItem("datakeel.ask.conversation", "thread-1");
  const second = {
    ...first,
    id: "answer-2",
    conversation_id: "thread-2",
    question: "Current new question",
    interpreted_question: "Current complete question",
    result: { columns: ["value"], rows: [[222]], truncated: false },
  };
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(conversation)))
    .mockResolvedValueOnce(new Response(JSON.stringify(second)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <I18nProvider>
      <LocaleSwitch />
      <AskPage onOpenReceipt={vi.fn()} />
    </I18nProvider>,
  );
  await screen.findByLabelText("Calculated result");
  await user.click(screen.getByRole("button", { name: "New conversation" }));
  await user.type(
    screen.getByRole("textbox", { name: "Business question" }),
    second.question,
  );
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  expect(await screen.findByLabelText("Calculated result")).toHaveTextContent(
    "222",
  );
  await user.click(
    screen.getByRole("button", { name: "Result visualization" }),
  );
  await waitFor(() => {
    expect(screen.getByLabelText("计算结果")).toHaveTextContent("222");
  });
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(sessionStorage.getItem("datakeel.ask.conversation")).toBe("thread-2");
});
