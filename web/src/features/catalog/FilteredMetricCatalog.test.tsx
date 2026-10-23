import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { FilteredMetricCatalog } from "./FilteredMetricCatalog";
import { column, impact, mockCatalogFetch, table } from "./fixtures";

it("lists only the metrics consuming the selected table and opens their definition", async () => {
  const fetch = mockCatalogFetch();
  const user = userEvent.setup();
  render(
    <FilteredMetricCatalog
      table={table.asset_ref.asset_id}
      column=""
      onOpenReceipt={vi.fn()}
    />,
  );
  const list = screen.getByRole("region", { name: "Metrics" });
  await user.click(
    await within(list).findByRole("button", { name: "Retail revenue" }),
  );
  expect(await screen.findByText("Retail team")).toBeVisible();
  expect(
    fetch.mock.calls.some(
      ([path]) =>
        path ===
        `/api/catalog/tables/${encodeURIComponent(table.asset_ref.asset_id)}`,
    ),
  ).toBe(true);
  expect(
    within(list).getByRole("link", { name: "Clear filter" }),
  ).toHaveAttribute("href", "#/catalog?kind=metric");
});
it("uses asset_ref types to isolate consuming metrics from a column's mixed neighbors", async () => {
  const base = mockCatalogFetch();
  const neighbors = vi.fn<(path: string) => void>();
  vi.stubGlobal("fetch", (path: string, init?: RequestInit) => {
    if (path.startsWith("/api/catalog/neighbors?")) {
      neighbors(path);
      return Promise.resolve(new Response(JSON.stringify(impact)));
    }
    return base(path, init);
  });
  render(
    <FilteredMetricCatalog
      table=""
      column={column.asset_ref.asset_id}
      onOpenReceipt={vi.fn()}
    />,
  );
  const list = screen.getByRole("region", { name: "Metrics" });
  expect(
    await within(list).findByRole("button", { name: "Retail revenue" }),
  ).toBeVisible();
  expect(
    within(list).queryByRole("button", { name: "orders" }),
  ).not.toBeInTheDocument();
  expect(
    within(list).queryByRole("button", { name: "paid_amount" }),
  ).not.toBeInTheDocument();
  expect(within(list).getAllByRole("button")).toHaveLength(1);
  expect(neighbors).toHaveBeenCalledWith(
    `/api/catalog/neighbors?${new URLSearchParams({ asset_id: column.asset_ref.asset_id }).toString()}`,
  );
});
