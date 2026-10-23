import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { CatalogBrowser } from "./CatalogBrowser";
import { mockCatalogFetch, source, table } from "./fixtures";

it("navigates a source, its tables, and the selected table fields", async () => {
  const fetch = mockCatalogFetch();
  const user = userEvent.setup();
  render(<CatalogBrowser onOpenReceipt={vi.fn()} />);
  expect(
    screen.getByText("Select a source to browse its tables."),
  ).toBeVisible();
  await user.click(
    await screen.findByRole("button", { name: new RegExp(source.name) }),
  );
  await user.click(
    await screen.findByRole("button", { name: /orders ecommerce/ }),
  );
  expect(await screen.findByText("paid_amount")).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("parent_id=ecommerce"),
    expect.any(Object),
  );
  expect(fetch).toHaveBeenCalledWith(
    `/api/catalog/tables/${encodeURIComponent(table.asset_ref.asset_id)}`,
    expect.any(Object),
  );
});
