import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { AskChart } from "./AskChart";
import { retailAnswer } from "./testFixtures";

import type { ChartSpec, ChartType } from "./chartData";

const previousSql = {
  metric_id: "retail_revenue",
  metric_version: 2,
  source_id: "demo",
  dialect: "sqlite" as const,
  sql: 'SELECT SUM(amount) AS "value" FROM orders',
  parameters: {},
  tables: ["demo/main/orders"],
  columns: ["demo/main/orders/amount"],
};

const chart: ChartSpec = {
  type: "bar",
  title: "Revenue by region",
  description: "Registered revenue; source row order.",
  x: "region",
  y: ["value"],
  series: null,
  unit: "CNY",
  number_format: "number",
  sort: "source",
  available_types: ["bar", "horizontal_bar", "table"],
  show_percent: false,
};
const result = {
  columns: ["region", "value"],
  rows: [
    ["East", 1234.56789],
    ["West", -25],
    ["South", null],
  ],
  truncated: false,
};

it("renders accessible SVG from exact rows and supports keyboard switching to the same values", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <AskChart
      answer={{ ...retailAnswer, result }}
      chart={chart}
      footnotes={[]}
    />,
  );
  const image = screen.getByRole("img");
  expect(
    screen.queryByRole("button", { name: "Horizontal bars" }),
  ).not.toBeInTheDocument();
  expect(image).toHaveAccessibleName(/Retail revenue/);
  expect(image).toHaveAccessibleDescription();
  expect(image.querySelector("desc")).toHaveTextContent(
    "same result rows as the table",
  );
  expect(
    [...container.querySelectorAll("g[data-value]")].map((item) =>
      item.getAttribute("data-value"),
    ),
  ).toEqual(["1234.56789", "-25"]);
  const tableButton = screen.getByRole("button", { name: "Table" });
  tableButton.focus();
  await user.keyboard("{Enter}");
  const table = screen.getByRole("table", { name: "Result rows" });
  expect(within(table).getByText("1,234.56789 CNY")).toBeVisible();
  expect(within(table).getByText("-25 CNY")).toBeVisible();
  expect(within(table).getByText("No value")).toBeVisible();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  const automaticButton = screen.getByRole("button", { name: "Columns" });
  automaticButton.focus();
  await user.keyboard("{Enter}");
  expect(automaticButton).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("img")).toBeVisible();
});

it.each([
  "line",
  "bar",
  "horizontal_bar",
  "grouped_bar",
  "stacked_bar",
] as const)(
  "renders %s and negative geometry without introducing data",
  (type: ChartType) => {
    const groupedResult = {
      columns: ["region", "channel", "value"],
      rows: [
        ["East", "Shop", 10],
        ["East", "Web", -5],
        ["West", "Shop", 20],
        ["West", "Web", 30],
      ],
      truncated: false,
    };
    const { container } = render(
      <AskChart
        answer={{ ...retailAnswer, result: groupedResult }}
        chart={{
          ...chart,
          type,
          series: "channel",
          available_types: [type, "table"],
        }}
        footnotes={[]}
      />,
    );
    expect(screen.getByRole("img")).toBeVisible();
    expect(container.querySelectorAll("g[data-value]")).toHaveLength(4);
    for (const rect of container.querySelectorAll("rect")) {
      expect(Number(rect.getAttribute("width"))).toBeGreaterThanOrEqual(0);
      expect(Number(rect.getAttribute("height"))).toBeGreaterThanOrEqual(0);
    }
  },
);

it("shows scalar units, measured changes, and percentages without multiplying twice", () => {
  render(
    <AskChart
      answer={{
        ...retailAnswer,
        result: { columns: ["value"], rows: [[120]], truncated: false },
        comparison: {
          mode: "year_over_year",
          previous_sql: previousSql,
          previous_time_range: { start: "2025-07-01", end: "2025-10-01" },
          previous_result: {
            columns: ["value"],
            rows: [[100]],
            truncated: false,
          },
          changes: [
            {
              dimensions: [],
              current_value: 120,
              previous_value: 100,
              delta: 20,
              percent_change: 20,
            },
          ],
        },
      }}
      chart={{ ...chart, type: "scalar", available_types: ["scalar", "table"] }}
      footnotes={[]}
    />,
  );
  expect(screen.getByLabelText("Calculated result")).toHaveTextContent("120");
  expect(
    screen.getByText("Change from same period last year: 20 CNY (20%)"),
  ).toBeVisible();
});

it("reports unavailable previous data, preserves booleans, and formats contract percentages", () => {
  const missing = {
    mode: "year_over_year" as const,
    previous_sql: previousSql,
    previous_time_range: { start: "2025-07-01", end: "2025-10-01" },
    previous_result: { columns: ["value"], rows: [], truncated: false },
    changes: [
      {
        dimensions: [],
        current_value: 0.25,
        previous_value: null,
        delta: null,
        percent_change: null,
      },
    ],
  };
  const { rerender } = render(
    <AskChart
      answer={{
        ...retailAnswer,
        result: { columns: ["value"], rows: [[0.25]], truncated: false },
        comparison: missing,
      }}
      chart={{
        ...chart,
        type: "scalar",
        number_format: "percent",
        available_types: ["scalar", "table"],
      }}
      footnotes={[]}
    />,
  );
  expect(screen.getByLabelText("Calculated result")).toHaveTextContent("25%");
  expect(screen.getByText(/No previous data/)).toBeVisible();
  rerender(
    <AskChart
      key="table"
      answer={{
        ...retailAnswer,
        result: {
          columns: ["active"],
          rows: [[true], [false]],
          truncated: false,
        },
      }}
      chart={{
        ...chart,
        type: "table",
        available_types: ["table", "bar", "table"],
      }}
      footnotes={[]}
    />,
  );
  expect(screen.getByText("Yes")).toBeVisible();
  expect(screen.getByText("No")).toBeVisible();
  expect(screen.getAllByRole("button", { name: "Table" })).toHaveLength(1);
  expect(
    screen.queryByRole("button", { name: "Columns" }),
  ).not.toBeInTheDocument();
});

it("keeps a missing-baseline notice visible for grouped charts and the table view", async () => {
  const user = userEvent.setup();
  render(
    <AskChart
      answer={{
        ...retailAnswer,
        result,
        comparison: {
          mode: "year_over_year",
          previous_sql: previousSql,
          previous_time_range: { start: "2025-07-01", end: "2025-10-01" },
          previous_result: {
            columns: ["region", "value"],
            rows: [["East", 100]],
            truncated: false,
          },
          changes: [
            {
              dimensions: ["East"],
              current_value: 1234.56789,
              previous_value: 100,
              delta: 1134.56789,
              percent_change: 1134.56789,
            },
            {
              dimensions: ["West"],
              current_value: -25,
              previous_value: null,
              delta: null,
              percent_change: null,
            },
          ],
        },
      }}
      chart={chart}
      footnotes={[]}
    />,
  );
  expect(
    screen.getByText(
      "Some categories have no previous data. Their changes cannot be calculated.",
    ),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Table" }));
  expect(
    screen.getByText(
      "Some categories have no previous data. Their changes cannot be calculated.",
    ),
  ).toBeVisible();
});
