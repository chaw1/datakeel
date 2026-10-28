import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { AskChart } from "./AskChart";
import { retailAnswer } from "./testFixtures";

import type { ChartSpec } from "./chartData";
import type { AskAnswer } from "../../api/ask";

const chart: ChartSpec = {
  type: "scalar",
  title: "Revenue",
  description: "Generated rows",
  x: null,
  y: ["value"],
  series: null,
  unit: "CNY",
  number_format: "number",
  sort: "source",
  available_types: ["scalar", "table"],
  show_percent: false,
};
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
const comparison: NonNullable<AskAnswer["comparison"]> = {
  mode: "year_over_year",
  previous_sql: previousSql,
  previous_time_range: { start: "2025-07-01", end: "2025-10-01" },
  previous_result: { columns: ["value"], rows: [[0]], truncated: false },
  changes: [],
};
const zeroNotice =
  "The previous value is zero. Percentage change cannot be calculated for that value.";

it.each([
  [0, "year_over_year", "Change from same period last year"],
  [10, "year_over_year", "Change from same period last year"],
  [10, "period_over_period", "Change from previous period"],
] as const)(
  "shows a measured delta of %s for %s under the matching baseline label and explains the zero denominator",
  (value, mode, label) => {
    render(
      <AskChart
        answer={{
          ...retailAnswer,
          result: { columns: ["value"], rows: [[value]], truncated: false },
          comparison: {
            ...comparison,
            mode,
            changes: [
              {
                dimensions: [],
                current_value: value,
                previous_value: 0,
                delta: value,
                percent_change: null,
              },
            ],
          },
        }}
        chart={chart}
        footnotes={[]}
      />,
    );
    expect(screen.getByText(`${label}: ${String(value)} CNY`)).toBeVisible();
    expect(
      screen.queryByText(
        mode === "year_over_year"
          ? /Change from previous period/
          : /same period last year/,
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByText(zeroNotice)).toBeVisible();
    expect(screen.queryByText(/No previous data/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Infinity|NaN/)).not.toBeInTheDocument();
  },
);

it("explains zero and absent baselines independently for groups and preserves both notices in table view", async () => {
  const user = userEvent.setup();
  render(
    <AskChart
      answer={{
        ...retailAnswer,
        result: {
          columns: ["region", "value"],
          rows: [
            ["East", 10],
            ["West", 20],
          ],
          truncated: false,
        },
        comparison: {
          ...comparison,
          previous_result: {
            columns: ["region", "value"],
            rows: [["East", 0]],
            truncated: false,
          },
          changes: [
            {
              dimensions: ["East"],
              current_value: 10,
              previous_value: 0,
              delta: 10,
              percent_change: null,
            },
            {
              dimensions: ["West"],
              current_value: 20,
              previous_value: null,
              delta: null,
              percent_change: null,
            },
          ],
        },
      }}
      chart={{
        ...chart,
        type: "bar",
        x: "region",
        available_types: ["bar", "table"],
      }}
      footnotes={[]}
    />,
  );
  const missingNotice =
    "Some categories have no previous data. Their changes cannot be calculated.";
  expect(screen.getByText(zeroNotice)).toBeVisible();
  expect(screen.getByText(missingNotice)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Table" }));
  expect(screen.getByText(zeroNotice)).toBeVisible();
  expect(screen.getByText(missingNotice)).toBeVisible();
});
