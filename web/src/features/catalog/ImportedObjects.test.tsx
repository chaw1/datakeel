import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { page, table } from "./fixtures";
import { ImportedObjects } from "./ImportedObjects";

it("browses extended object types and opens lineage with fresh integration details", async () => {
  const item = {
    ...table,
    name: "daily_orders",
    asset_ref: { ...table.asset_ref, asset_type: "dag" },
    properties: {
      integration: {
        system: "airflow",
        unique_id: "daily_orders",
        details: { state: "success", last_success: "2026-10-26T10:00:00Z" },
      },
    },
  };
  const fetch = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify(page([item])))),
    );
  vi.stubGlobal("fetch", fetch);
  const open = vi.fn();
  const user = userEvent.setup();
  render(<ImportedObjects onOpenReceipt={open} />);
  await user.selectOptions(screen.getByLabelText("Object type"), "dag");
  await user.click(
    await screen.findByRole("button", { name: "daily_orders dag" }),
  );
  expect(screen.getByText("2026-10-26T10:00:00Z")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "View lineage" }));
  expect(open).toHaveBeenCalledWith({
    assetId: item.asset_ref.asset_id,
    includeCatalog: true,
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/catalog/import/objects?limit=20&offset=0&kind=dag",
    expect.any(Object),
  );
});
