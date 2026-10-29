import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AskAnswerView } from "./AskAnswerView";
import { AskChart } from "./AskChart";
import { retailAnswer } from "./testFixtures";

import type { ChartSpec } from "./chartData";

const chart: ChartSpec = {
  type: "line",
  title: "Revenue",
  description: "Generated rows",
  x: "category",
  y: ["value"],
  series: null,
  unit: "CNY",
  number_format: "number",
  sort: "source",
  available_types: ["line", "bar", "table"],
  show_percent: false,
};

it.each([12, 30])(
  "keeps all %s measurements while spacing at most six vertical axis labels",
  (count) => {
    const rows = Array.from({ length: count }, (_, index) => [
      count === 12
        ? `2026-${String(index + 1).padStart(2, "0")}-01`
        : `Region ${String(index)}`,
      index,
    ]);
    const { container } = render(
      <AskAnswerView
        answer={{
          ...retailAnswer,
          result: { columns: ["category", "value"], rows, truncated: false },
          chart: { ...chart, type: count === 12 ? "line" : "grouped_bar" },
        }}
        onOpenReceipt={vi.fn()}
      />,
    );
    expect(container.querySelectorAll("g[data-value]")).toHaveLength(count);
    expect(
      container.querySelectorAll("text[data-category-index]"),
    ).toHaveLength(6);
    expect(
      container.querySelectorAll("text[data-category-index] title"),
    ).toHaveLength(6);
    expect(container.querySelectorAll("g[data-value] title")).toHaveLength(
      count,
    );
  },
);

it("fits long Chinese horizontal labels into their margin while preserving full table values", async () => {
  const user = userEvent.setup();
  const label = "一二三四五六七八九十一二三四五六七八";
  const { container } = render(
    <AskAnswerView
      answer={{
        ...retailAnswer,
        result: {
          columns: ["category", "value"],
          rows: [[label, 10]],
          truncated: false,
        },
        chart: {
          ...chart,
          type: "horizontal_bar",
          available_types: ["horizontal_bar", "table"],
        },
      }}
      onOpenReceipt={vi.fn()}
    />,
  );
  const axisLabel = container.querySelector("text[data-category-index]");
  expect(axisLabel?.querySelector("title")).toHaveTextContent(label);
  expect(axisLabel?.lastChild?.textContent?.length).toBeLessThanOrEqual(10);
  expect(axisLabel?.lastChild?.textContent).toContain("…");
  await user.click(screen.getByRole("button", { name: "Table" }));
  expect(within(screen.getByRole("table")).getByText(label)).toBeVisible();
});

it("starts each answer in its declared chart view and preserves numeric dimension labels", async () => {
  const user = userEvent.setup();
  const first = {
    ...retailAnswer,
    id: "chart-1",
    result: {
      columns: ["category", "value"],
      rows: [[2026, 0.25]],
      truncated: false,
    },
    chart: {
      ...chart,
      type: "bar" as const,
      number_format: "percent" as const,
      unit: null,
      available_types: ["bar", "table"] as const,
    },
  };
  const { rerender } = render(
    <AskAnswerView
      answer={{
        ...first,
        chart: {
          ...first.chart,
          available_types: [...first.chart.available_types],
        },
      }}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Table" }));
  const table = screen.getByRole("table");
  expect(within(table).getByText("2026")).toBeVisible();
  expect(within(table).getByText("25%")).toBeVisible();
  rerender(
    <AskAnswerView
      answer={{ ...retailAnswer, id: "chart-2", result: first.result, chart }}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByRole("button", { name: "Line" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Columns" }),
  ).not.toBeInTheDocument();
});

it("shows share labels alongside raw metric values and does not manufacture empty results", () => {
  const { rerender } = render(
    <AskChart
      answer={{
        ...retailAnswer,
        result: {
          columns: ["region", "value"],
          rows: [
            ["A", 1],
            ["B", 3],
          ],
          truncated: false,
        },
      }}
      chart={{ ...chart, type: "bar", x: "region", show_percent: true }}
      footnotes={[]}
    />,
  );
  expect(screen.getByText("25%")).toBeVisible();
  expect(screen.getByText("75%")).toBeVisible();
  rerender(
    <AskChart
      answer={{
        ...retailAnswer,
        result: { columns: ["value"], rows: [], truncated: false },
      }}
      chart={{ ...chart, type: "bar", x: "region" }}
      footnotes={[]}
    />,
  );
  expect(screen.getByText("No rows matched this question.")).toBeVisible();
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
});
