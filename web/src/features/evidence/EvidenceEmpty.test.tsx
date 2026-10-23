import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { dataset, version } from "../../test/fixtures";

import { EvidenceEmpty } from "./EvidenceEmpty";
import { initialFilters } from "./query";

it("distinguishes an empty dataset and gives the data library entry", () => {
  render(
    <EvidenceEmpty
      datasetId={dataset.id}
      dataset={{ ...dataset, file_count: 0 }}
      filters={initialFilters}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByText("This dataset has no samples.")).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Open data library" }),
  ).toHaveAttribute("href", "#/datasets");
});
it("names the active condition and removes only that condition", async () => {
  const user = userEvent.setup();
  const change = vi.fn();
  render(
    <EvidenceEmpty
      datasetId={dataset.id}
      dataset={dataset}
      filters={{ ...initialFilters, split: "val", qualityMax: 0 }}
      onChange={change}
    />,
  );
  expect(
    screen.getByText("No samples match the current conditions."),
  ).toBeVisible();
  await user.click(
    screen.getByRole("button", { name: "Remove Maximum quality" }),
  );
  expect(change).toHaveBeenCalledWith({ ...initialFilters, split: "val" });
});
it("explains unsupported ordinary files without offering a fake extraction draft", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify([version]))),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <EvidenceEmpty
      datasetId={dataset.id}
      dataset={dataset}
      filters={initialFilters}
      onChange={vi.fn()}
    />,
  );
  expect(
    screen.getByText("Extractors have not produced evidence for these files."),
  ).toBeVisible();
  expect(await screen.findByText(/imported as ordinary files/)).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Prepare evidence extraction" }),
  ).not.toBeInTheDocument();
  expect(document.querySelector('a[href^="#/agent"]')).not.toBeInTheDocument();
  expect(
    screen.getByText("Generate or import paired samples locally"),
  ).toBeVisible();
  await userEvent
    .setup()
    .click(screen.getByText("Generate or import paired samples locally"));
  expect(
    screen.getByText(/from datakeel.storage.evidence_import/),
  ).toBeVisible();
  expect(screen.getByText(/DATAKEEL_HOME/)).toBeVisible();
  expect(fetch).toHaveBeenCalledExactlyOnceWith(
    `/api/datasets/${dataset.id}/versions`,
    expect.objectContaining({ method: "GET" }),
  );
});
