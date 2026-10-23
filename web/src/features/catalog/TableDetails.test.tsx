import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { mockCatalogFetch, table } from "./fixtures";
import { TableDetails } from "./TableDetails";

it("shows owners, consuming metrics, field properties, and impact on demand", async () => {
  mockCatalogFetch();
  const user = userEvent.setup();
  const open = vi.fn();
  render(
    <TableDetails tableId={table.asset_ref.asset_id} onOpenReceipt={open} />,
  );
  expect(await screen.findByText("paid_amount")).toBeVisible();
  expect(screen.getAllByText("INTEGER")).toHaveLength(2);
  expect(screen.getByText(/Not registered/)).toBeVisible();
  await user.click(
    screen.getByRole("button", { name: "Downstream impact: paid_amount" }),
  );
  const impact = await screen.findByRole("region", {
    name: "Downstream impact",
  });
  expect(
    await within(impact).findByRole("button", { name: "Retail revenue" }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "View lineage" }));
  expect(open).toHaveBeenCalledWith({
    assetId: table.asset_ref.asset_id,
    includeCatalog: true,
  });
});
