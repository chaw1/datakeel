import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { mockCatalogFetch } from "./fixtures";
import { Glossary } from "./Glossary";

it("displays glossary synonyms and connects meaning to bounded lineage", async () => {
  mockCatalogFetch();
  const open = vi.fn();
  const user = userEvent.setup();
  render(<Glossary onOpenReceipt={open} />);
  expect(await screen.findByText("Retail receipts")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "retail_revenue" }));
  expect(open).toHaveBeenCalledWith({
    assetId: "term/Retail",
    includeCatalog: true,
  });
});
