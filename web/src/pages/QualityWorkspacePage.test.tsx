import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { dashboard } from "../test/dashboardFixtures";

import { QualityWorkspacePage } from "./QualityWorkspacePage";

it("preserves the workbench alert filter and links to the matching dataset quality", () => {
  render(<QualityWorkspacePage datasets={dashboard.datasets} alertsOnly />);
  expect(screen.getByRole("checkbox")).toBeChecked();
  expect(screen.getByText("Sample collection")).toBeVisible();
  expect(screen.queryByText("Boundary dataset")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Details" })).toHaveAttribute(
    "href",
    "#/object/dataset/dataset-1?tab=quality",
  );
});
