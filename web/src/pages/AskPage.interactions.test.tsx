import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import {
  candidateMetrics,
  retailAnswer,
  unavailableAnswer,
} from "../features/ask/testFixtures";

import { AskPage } from "./AskPage";

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

it.each(["上个季度营业额是多少", "上个季度出货额和零售额是多少"])(
  "pins a selected definition and repeats the original question: %s",
  async (question) => {
    const user = userEvent.setup();
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...unavailableAnswer,
            question,
            status: "clarification",
            candidates: candidateMetrics.slice(0, 2),
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...retailAnswer, question })),
      );
    vi.stubGlobal("fetch", fetch);
    const { container } = render(<AskPage onOpenReceipt={vi.fn()} />);
    await user.type(
      screen.getByRole("textbox", { name: "Business question" }),
      question,
    );
    await user.click(screen.getByRole("button", { name: "Ask data" }));
    const choices = await screen.findAllByRole("button", {
      name: /Version 2 · Owner:/,
    });
    expect(choices).toHaveLength(2);
    expect(
      container.querySelectorAll(".ask-clarification-question"),
    ).toHaveLength(1);
    expect(choices[0]).toHaveTextContent("sum(");
    await user.clear(
      screen.getByRole("textbox", { name: "Business question" }),
    );
    await user.type(
      screen.getByRole("textbox", { name: "Business question" }),
      "An unrelated edited question",
    );
    await user.click(choices[0]);
    expect(await screen.findByLabelText("Calculated result")).toHaveTextContent(
      "4,979,475",
    );
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/ask",
      expect.objectContaining({
        body: JSON.stringify({
          actor: "local-user",
          question,
          reference_instant: unavailableAnswer.reference_instant,
          session_id: unavailableAnswer.session_id,
          metric_id: "retail_revenue",
        }),
      }),
    );
  },
);

it("prefills the hash question and metric without sending until submit and blocks IME submissions", async () => {
  window.history.replaceState(
    null,
    "",
    `/#/ask?question=${encodeURIComponent(retailAnswer.question)}&metric=retail_revenue`,
  );
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify(retailAnswer)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const { container } = render(<AskPage onOpenReceipt={vi.fn()} />);
  const input = screen.getByRole("textbox", { name: "Business question" });
  expect(input).toHaveValue(retailAnswer.question);
  expect(screen.getByText("retail_revenue")).toBeVisible();
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.compositionStart(input);
  const form = container.querySelector("form");
  if (!form) throw new Error("Missing question form");
  fireEvent.submit(form);
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.compositionEnd(input);
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  expect(await screen.findByLabelText("Calculated result")).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    "/api/ask",
    expect.objectContaining({
      body: JSON.stringify({
        actor: "local-user",
        metric_id: "retail_revenue",
        question: retailAnswer.question,
        reference_instant: "2026-10-01T00:00:00Z",
      }),
    }),
  );
});

it("generates a refusal follow-up locally with the actual reason and no extra request", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify(unavailableAnswer)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  await user.click(
    screen.getByRole("button", { name: "Why did the return rate rise?" }),
  );
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  await user.click(
    await screen.findByRole("button", {
      name: "Ask the metric owner to add a definition",
    }),
  );
  const draft = screen.getByRole<HTMLTextAreaElement>("textbox", {
    name: "Metric request draft",
  }).value;
  expect(draft).toContain(unavailableAnswer.message);
  expect(draft).toContain(unavailableAnswer.question);
  expect(fetch).toHaveBeenCalledTimes(1);
});
