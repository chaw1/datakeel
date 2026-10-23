import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { metric, mockCatalogFetch } from "./fixtures";
import { MetricDetails } from "./MetricDetails";

it("exposes the current version, JSON history, and a controlled editor", async () => {
  mockCatalogFetch();
  const user = userEvent.setup();
  render(
    <MetricDetails metricId={metric.definition.id} onOpenReceipt={vi.fn()} />,
  );
  expect(
    await screen.findByRole("link", { name: "View version history (JSON)" }),
  ).toHaveAttribute("href", "/api/catalog/metrics/retail_revenue/history");
  await user.click(screen.getByRole("button", { name: "Edit definition" }));
  expect(await screen.findByLabelText("Metric name")).toHaveValue(
    "Retail revenue",
  );
  await user.click(screen.getByRole("button", { name: "Close editor" }));
  expect(screen.queryByLabelText("Metric name")).not.toBeInTheDocument();
});

it("retains unresolved definitions and displays their missing-reference reasons", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ...metric,
          status: "unresolved",
          reasons: ["Missing column: ecommerce/main/orders/missing"],
        }),
      ),
    ),
  );
  render(
    <MetricDetails metricId={metric.definition.id} onOpenReceipt={vi.fn()} />,
  );
  expect(await screen.findByText("Missing references")).toBeVisible();
  expect(
    screen.getByText("Missing column: ecommerce/main/orders/missing"),
  ).toBeVisible();
});

it("uses the same localized sample name as the relationship card", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ...metric,
          definition: { ...metric.definition, name: "零售额" },
        }),
      ),
    ),
  );
  render(
    <MetricDetails metricId={metric.definition.id} onOpenReceipt={vi.fn()} />,
  );
  expect(
    await screen.findByRole("heading", { name: "Retail revenue" }),
  ).toBeVisible();
});
