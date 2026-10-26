import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { standard, standardsPlan } from "../standards/fixtures";

import { ApprovalObjects } from "./ApprovalObjects";

it("shows the frozen mapping column and target instead of claiming that no objects are affected", () => {
  render(<ApprovalObjects plan={standardsPlan} />);
  expect(
    screen.getByRole("region", { name: "Affected standards objects · 1" }),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "retail/main/customers/cust_no" }),
  ).toHaveAttribute(
    "href",
    "#/object/column/retail%2Fmain%2Fcustomers%2Fcust_no?tab=facts",
  );
  expect(screen.getByText("customer_id")).toBeVisible();
  expect(
    screen.queryByText("No objects are selected in this plan."),
  ).not.toBeInTheDocument();
});

it("shows a frozen standard definition and rollback revision", () => {
  const { rerender } = render(
    <ApprovalObjects
      plan={{
        ...standardsPlan,
        action_type: "update_standard",
        canonical_params: { definition: standard },
      }}
    />,
  );
  expect(screen.getByText("Customer identifier")).toBeVisible();
  rerender(
    <ApprovalObjects
      plan={{
        ...standardsPlan,
        action_type: "rollback_standards",
        canonical_params: { revision: 2 },
      }}
    />,
  );
  expect(screen.getByText("Revision 2")).toBeVisible();
});
