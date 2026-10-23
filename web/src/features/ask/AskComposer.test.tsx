import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AskComposer } from "./AskComposer";

it("selects a demo question and submits an editable UTC reference date", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(<AskComposer busy={false} onSubmit={onSubmit} />);
  const reference = screen.getByLabelText("Calculation reference date (UTC)");
  expect(reference).toHaveValue("2026-10-01");
  expect(screen.getByRole("button", { name: "Ask data" })).toBeDisabled();
  await user.click(
    screen.getByRole("button", {
      name: "East China retail revenue · last quarter",
    }),
  );
  expect(
    screen.getByRole("textbox", { name: "Business question" }),
  ).toHaveFocus();
  fireEvent.change(reference, { target: { value: "2026-07-01" } });
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  expect(onSubmit).toHaveBeenCalledWith({
    question: "上个季度华东区零售额是多少",
    reference_instant: "2026-07-01T00:00:00Z",
    actor: "local-user",
  });
});

it("normalizes the question and blocks empty input and busy submissions", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  const { rerender } = render(<AskComposer busy={false} onSubmit={onSubmit} />);
  const input = screen.getByRole("textbox");
  await user.type(input, "  ");
  expect(screen.getByRole("button", { name: "Ask data" })).toBeDisabled();
  await user.type(input, "Cafe\u0301");
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  expect(onSubmit).toHaveBeenCalledWith(
    expect.objectContaining({ question: "Café" }),
  );
  rerender(<AskComposer busy={true} onSubmit={onSubmit} />);
  expect(input).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Finding the metric and calculating…" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Revenue · compare definitions" }),
  ).toBeDisabled();
});
