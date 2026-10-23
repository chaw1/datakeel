import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { dataset, workspace } from "../test/fixtures";

import { FilesPage } from "./FilesPage";
it("renders file download links", () => {
  render(<FilesPage data={workspace} selectedId={dataset.id} />);
  expect(
    screen.getByRole("link", { name: "Download sample.txt" }),
  ).toHaveAttribute("href", "/api/datasets/dataset-1/files/file-1/download");
});
