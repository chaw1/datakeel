import { expect, it } from "vitest";

import { chartDomain, chartPoints } from "./chartData";

import type { ChartSpec } from "./chartData";

const chart: ChartSpec = {
  type: "bar",
  title: "Revenue",
  description: "Generated rows",
  x: "region",
  y: ["value"],
  series: null,
  unit: "CNY",
  number_format: "number",
  sort: "source",
  available_types: ["bar", "table"],
  show_percent: false,
};

it("uses signed stacked totals for the scale and skips absent measurements", () => {
  const points = chartPoints(
    {
      columns: ["region", "value"],
      rows: [
        ["East", -10],
        ["East", -20],
        ["East", 5],
        ["West", null],
      ],
      truncated: false,
    },
    chart,
  );
  expect(points).toHaveLength(3);
  expect(chartDomain(points, true)).toEqual({ minimum: -30, maximum: 5 });
  expect(chartDomain(points, false)).toEqual({ minimum: -20, maximum: 5 });
});
