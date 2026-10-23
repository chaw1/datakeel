import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { MetricEvidence } from "./MetricEvidence";
import { retailMetric } from "./testFixtures";

it("shows the full metric meaning, owner, version, caveats and history link", () => {
  render(<MetricEvidence metric={retailMetric} />);
  expect(screen.getByText("Version 2")).toBeVisible();
  expect(screen.getByText("retail-operations")).toBeVisible();
  expect(screen.getByText("sum(ecommerce/main/orders/amount)")).toBeVisible();
  expect(
    screen.getByText('ecommerce/main/orders/status eq "completed"'),
  ).toBeVisible();
  expect(screen.getByText("Excludes cancelled orders.")).toBeVisible();
  expect(
    screen.getByRole("link", { name: "View metric history (JSON)" }),
  ).toHaveAttribute("href", "/api/catalog/metrics/retail_revenue/history");
});

it("makes absent fixed filters and caveats explicit", () => {
  render(
    <MetricEvidence
      metric={{
        ...retailMetric,
        definition: { ...retailMetric.definition, filters: [], caveats: [] },
      }}
    />,
  );
  expect(screen.getByText("No fixed filters")).toBeVisible();
  expect(
    screen.getByText("No additional caveats are registered."),
  ).toBeVisible();
});
