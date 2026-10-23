import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { column, impact, mockCatalogFetch } from "./fixtures";
import { ImpactTree } from "./ImpactTree";

it("renders bounded dependency branches and opens catalog lineage", async () => {
  const fetch = mockCatalogFetch();
  const open = vi.fn();
  const user = userEvent.setup();
  render(
    <ImpactTree assetId={column.asset_ref.asset_id} onOpenReceipt={open} />,
  );
  await user.click(
    await screen.findByRole("button", { name: "Retail revenue" }),
  );
  expect(open).toHaveBeenCalledWith({
    assetId: "retail_revenue",
    includeCatalog: true,
  });
  expect(screen.getByRole("button", { name: "Retail" })).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("max_nodes=100"),
    expect.any(Object),
  );
});

it("reports truncated impact instead of implying complete coverage", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ ...impact, truncated: true })),
      ),
  );
  render(
    <ImpactTree assetId={column.asset_ref.asset_id} onOpenReceipt={vi.fn()} />,
  );
  expect(await screen.findByText(/result reached 100 objects/)).toBeVisible();
});
