import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { dataset, workspace } from "../test/fixtures";

import { ReportPage } from "./ReportPage";
it("renders report chapters", () => {
  render(<ReportPage data={workspace} selectedId={dataset.id} />);
  expect(
    screen.getByRole("heading", { name: "Dataset summary" }),
  ).toBeVisible();
});
