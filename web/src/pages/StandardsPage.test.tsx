import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { mockStandardsFetch } from "../features/standards/fixtures";

import { StandardsPage } from "./StandardsPage";

it("browses bilingual standard definitions, searches by status, and opens reference code values", async () => {
  const fetch = mockStandardsFetch();
  const user = userEvent.setup();
  render(<StandardsPage onDataChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  await user.click(
    await screen.findByRole("button", {
      name: /Customer identifier customer_id/,
    }),
  );
  expect(
    screen.getByText("Stable customer business identifier."),
  ).toBeVisible();
  expect(screen.getByText("cust_no")).toBeVisible();
  await user.type(
    screen.getByLabelText("Search standards or code lists"),
    "customer",
  );
  await user.selectOptions(
    screen.getByLabelText("Filter standard status"),
    "active",
  );
  expect(
    fetch.mock.calls.some(
      ([path]) =>
        path === "/api/standards/fields?search=customer&status=active",
    ),
  ).toBe(true);
  await user.click(screen.getByRole("button", { name: "Code lists" }));
  await user.click(
    await screen.findByRole("button", {
      name: /Customer status customer_status/,
    }),
  );
  expect(screen.getByRole("cell", { name: "Inactive" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Standards report" }));
  expect(
    await screen.findByRole("heading", { name: "Standards report" }),
  ).toBeVisible();
});
