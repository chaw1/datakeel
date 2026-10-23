import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { mockCatalogFetch } from "./fixtures";
import { MetricCatalog } from "./MetricCatalog";

it("selects a registered metric and shows its authoritative card", async () => {
  mockCatalogFetch();
  const user = userEvent.setup();
  render(<MetricCatalog onOpenReceipt={vi.fn()} />);
  await user.click(
    await screen.findByRole("button", {
      name: /Retail revenue retail_revenue/,
    }),
  );
  expect(await screen.findByText("Retail team")).toBeVisible();
  expect(screen.getByText("Synthetic amounts in yuan.")).toBeVisible();
});
