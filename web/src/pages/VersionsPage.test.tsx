import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { dataset, workspace } from "../test/fixtures";

import { VersionsPage } from "./VersionsPage";
it("renders immutable version snapshots", () => {
  render(<VersionsPage data={workspace} selectedId={dataset.id} />);
  expect(
    screen.getByRole("heading", { name: "Version history" }),
  ).toBeVisible();
});
