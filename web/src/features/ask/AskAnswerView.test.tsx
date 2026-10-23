import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AskAnswerView } from "./AskAnswerView";
import { retailAnswer, unavailableAnswer } from "./testFixtures";

it("renders a scalar with explicit half-open dates and the applied metric definition", async () => {
  const user = userEvent.setup();
  render(<AskAnswerView answer={retailAnswer} onOpenReceipt={vi.fn()} />);
  expect(screen.getByLabelText("Calculated result")).toHaveTextContent(
    "4,979,475",
  );
  expect(screen.getByLabelText("Calculated result")).toHaveClass(
    "answer-number",
  );
  expect(screen.getAllByRole("link", { name: /^[a-d] ·/ })).toHaveLength(4);
  await user.click(screen.getByRole("link", { name: "d · Time interval" }));
  expect(screen.getByText("[2026-07-01, 2026-10-01)")).toBeVisible();
  expect(screen.getByText("Start included; end excluded.")).toBeVisible();
  expect(
    screen.getByText("Reference date used · 10-01 00:00 UTC"),
  ).toBeVisible();
  await user.click(screen.getByRole("link", { name: "a · Metric definition" }));
  expect(screen.getByText("Version 2")).toBeVisible();
  expect(screen.getByText("10-01 00:00 UTC")).toHaveAttribute(
    "datetime",
    retailAnswer.reference_instant,
  );
});

it("renders table cells faithfully, including null and boolean values", () => {
  render(
    <AskAnswerView
      answer={{
        ...retailAnswer,
        result: {
          columns: ["region", "total", "active"],
          rows: [
            ["华东", 1234.5, true],
            ["华南", null, false],
          ],
          truncated: true,
        },
      }}
      onOpenReceipt={vi.fn()}
    />,
  );
  const table = screen.getByRole("table", { name: "Result rows" });
  expect(within(table).getAllByRole("row")).toHaveLength(3);
  expect(within(table).getByText("1,234.5")).toBeVisible();
  expect(within(table).getByText("No value")).toBeVisible();
  expect(within(table).getByText("Yes")).toBeVisible();
  expect(within(table).getByText("No")).toBeVisible();
  expect(
    screen.getByText(
      "The row limit was reached. Refine the question to see more.",
    ),
  ).toBeVisible();
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
});

it.each(["unanswerable", "clarification"] as const)(
  "shows %s candidates without a numerical answer",
  (status) => {
    const candidates =
      status === "clarification"
        ? unavailableAnswer.candidates.slice(0, 2)
        : unavailableAnswer.candidates;
    render(
      <AskAnswerView
        answer={{ ...unavailableAnswer, status, candidates }}
        onOpenReceipt={vi.fn()}
      />,
    );
    const list = screen.getByRole("list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(
      status === "clarification" ? 2 : 3,
    );
    expect(
      screen.getByRole("heading", {
        name:
          status === "clarification"
            ? "Choose the business definition first"
            : "No registered metric can answer this question",
      }),
    ).toBeVisible();
    expect(
      screen.queryByLabelText("Calculated result"),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(
      screen.queryByText("SQL and bound parameters"),
    ).not.toBeInTheDocument();
  },
);

it("does not turn an empty result into a zero", () => {
  render(
    <AskAnswerView
      answer={{
        ...retailAnswer,
        result: { columns: ["value"], rows: [], truncated: false },
      }}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByText("No rows matched this question.")).toBeVisible();
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
});
