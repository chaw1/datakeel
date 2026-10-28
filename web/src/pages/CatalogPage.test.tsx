import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { mockCatalogFetch } from "../features/catalog/fixtures";

import { CatalogPage } from "./CatalogPage";

it("switches between source browsing, registered metrics, and the glossary", async () => {
  mockCatalogFetch();
  const user = userEvent.setup();
  render(<CatalogPage onOpenReceipt={vi.fn()} />);
  expect(
    screen.getByRole("heading", {
      name: /^Data catalog ·/,
    }),
  ).toBeVisible();
  expect(
    await screen.findByRole("button", { name: /Fictional Kitchen Ecommerce/ }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Metrics" }));
  expect(
    await screen.findByRole("button", {
      name: /Retail revenue retail_revenue/,
    }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Business glossary" }));
  expect(await screen.findByText("Retail receipts")).toBeVisible();
});

it("opens the metadata import form and imported object browser", async () => {
  mockCatalogFetch();
  const user = userEvent.setup();
  render(<CatalogPage onOpenReceipt={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: "Import metadata" }));
  expect(screen.getByLabelText("manifest.json (required)")).toBeVisible();
  expect(
    await screen.findByRole("region", { name: "Imported objects" }),
  ).toBeVisible();
});
