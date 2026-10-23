import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { dataset, file, version } from "../../test/fixtures";

import { readObjectTarget } from "./navigation";
import { ObjectSections } from "./ObjectSections";
import { objectData, sample } from "./testFixtures";

it("shows the file sample's quality and immutable source instead of the dataset score", () => {
  render(
    <ObjectSections
      target={{ kind: "file", id: file.id, tab: "quality" }}
      data={{ ...objectData, samples: [{ ...sample, quality_score: 17.2 }] }}
      reload={vi.fn()}
      onOpen={vi.fn()}
    />,
  );
  const quality = screen.getByRole("region", { name: "Quality score" });
  expect(within(quality).getByText("17.2", { exact: true })).toBeVisible();
  expect(screen.queryByText("83.5", { exact: true })).not.toBeInTheDocument();
  const source = within(quality).getByRole("link", { name: version.id });
  expect(readObjectTarget(source.getAttribute("href") ?? "")).toMatchObject({
    kind: "version",
    id: version.id,
    datasetId: dataset.id,
    tab: "facts",
  });
  expect(within(quality).getByText(/"quality_score": 17.2/)).toHaveTextContent(
    file.id,
  );
});

it("reports a missing file quality record without falling back to dataset quality", () => {
  render(
    <ObjectSections
      target={{ kind: "file", id: file.id, tab: "quality" }}
      data={{ ...objectData, samples: [] }}
      reload={vi.fn()}
      onOpen={vi.fn()}
    />,
  );
  expect(screen.getByText("Not recorded")).toBeVisible();
  expect(screen.queryByText("83.5", { exact: true })).not.toBeInTheDocument();
});

it("retains the complete dataset quality view for dataset objects", () => {
  render(
    <ObjectSections
      target={{ kind: "dataset", id: dataset.id, tab: "quality" }}
      data={objectData}
      reload={vi.fn()}
      onOpen={vi.fn()}
    />,
  );
  expect(screen.getByText("83.5", { exact: true })).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "A clearer picture of your data" }),
  ).toBeVisible();
});
