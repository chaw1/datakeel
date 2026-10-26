import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { mockStandardsFetch } from "./fixtures";
import { StandardsChecks } from "./StandardsChecks";

it("reads table conformance evidence and exposes redacted rule examples", async () => {
  const fetch = mockStandardsFetch();
  const user = userEvent.setup();
  render(<StandardsChecks tableId="retail/main/customers" />);
  const summary = await screen.findByText("Needs attention");
  await user.click(summary);
  expect(
    screen.getByRole("cell", {
      name: "Maximum customer identifier length exceeded",
    }),
  ).toBeVisible();
  expect(screen.getByRole("cell", { name: "[REDACTED]" })).toBeVisible();
  expect(fetch.mock.calls[0][0]).toBe(
    "/api/standards/report?table_id=retail%2Fmain%2Fcustomers",
  );
});
