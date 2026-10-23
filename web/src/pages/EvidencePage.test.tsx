import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import {
  evidenceDataset,
  evidenceResult,
  sample,
} from "../test/evidenceFixtures";
import { dataset } from "../test/fixtures";

import { EvidencePage } from "./EvidencePage";

it("selects the paired dataset, renders evidence, and clears checks when filters change", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(evidenceResult))),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <EvidencePage
      datasets={[{ ...dataset, id: "legacy" }, evidenceDataset]}
      datasetId="legacy"
      onDataChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Evidence dataset")).toHaveValue(
    evidenceDataset.id,
  );
  const checkbox = await screen.findByRole("checkbox", {
    name: `Select ${sample.filename}`,
  });
  await user.click(checkbox);
  expect(screen.getByRole("button", { name: "Create version" })).toBeEnabled();
  await user.selectOptions(screen.getByLabelText("Sample split"), "val");
  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: "Create version" }),
    ).toBeDisabled();
  });
  expect(await screen.findByText("82.5")).toBeVisible();
  expect(fetch).toHaveBeenCalled();
});
it("shows query failures and retries without claiming an empty successful query", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Read unavailable" }), {
        status: 500,
      }),
    )
    .mockResolvedValue(new Response(JSON.stringify(evidenceResult)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <EvidencePage
      datasets={[evidenceDataset]}
      datasetId={dataset.id}
      onDataChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "500 Read unavailable",
  );
  expect(
    screen.queryByText("No samples match these filters."),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(
    await screen.findByRole("checkbox", { name: `Select ${sample.filename}` }),
  ).toBeVisible();
});
