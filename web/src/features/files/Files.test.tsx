import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { workspace } from "../../test/fixtures";

import { Files } from "./Files";

it("filters files and switches to a frozen version manifest", async () => {
  const user = userEvent.setup();
  render(
    <Files
      files={workspace.files}
      versions={workspace.versions}
      datasetId="dataset-1"
    />,
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Filter modality" }),
    "image",
  );
  expect(screen.queryByText("sample.txt")).not.toBeInTheDocument();
  expect(screen.getByText("photo.png")).toBeVisible();
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Filter modality" }),
    "all",
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Select file version" }),
    "version-1",
  );
  expect(screen.getByText("processed.txt")).toBeVisible();
  expect(screen.queryByText("sample.txt")).not.toBeInTheDocument();
});

it("exposes quarantine state and does not offer deleted file downloads", () => {
  render(
    <Files
      files={workspace.files.map((file, index) => ({
        ...file,
        metadata: {
          ...file.metadata,
          quarantined: index === 0,
          deleted: index === 1,
        },
      }))}
      versions={[]}
      datasetId="dataset-1"
    />,
  );
  expect(screen.getByText("Quarantined")).toBeVisible();
  expect(screen.getByText("Deleted")).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Download sample.txt" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("link", { name: "Download photo.png" }),
  ).not.toBeInTheDocument();
});
