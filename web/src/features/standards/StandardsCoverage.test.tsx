import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { mockStandardsFetch } from "./fixtures";
import { StandardsCoverage } from "./StandardsCoverage";

it("shows real mapped-column coverage, owner and database groups, and violation ranking", async () => {
  mockStandardsFetch();
  const user = userEvent.setup();
  render(<StandardsCoverage />);
  expect(
    await screen.findByRole("link", { name: "retail/main/customers" }),
  ).toHaveAttribute(
    "href",
    "#/object/table/retail%2Fmain%2Fcustomers?tab=facts",
  );
  expect(
    screen.getByRole("heading", { name: "Violation Top 1" }),
  ).toBeVisible();
  expect(screen.getByRole("cell", { name: "Length" })).toBeVisible();
  await user.selectOptions(
    screen.getByLabelText("Group coverage by"),
    "owners",
  );
  expect(
    screen.getByRole("cell", { name: "Customer operations" }),
  ).toBeVisible();
  await user.selectOptions(
    screen.getByLabelText("Group coverage by"),
    "sources",
  );
  expect(screen.getByRole("cell", { name: "retail" })).toBeVisible();
});
