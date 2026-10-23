import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";
import { evidenceResult, sample } from "../../test/evidenceFixtures";

import { EvidenceExplorer } from "./EvidenceExplorer";

it.each([
  ["create_version_from_selection", "Create version"],
  ["quarantine_files", "Quarantine selection"],
])(
  "automatically executes %s using only checked versioned assets",
  async (action, label) => {
    const fetch = vi.fn((path: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            path.endsWith("/prepare")
              ? { ...actionPlan, action_type: action, reversible: true }
              : path.endsWith("/execute")
                ? { ...actionRun, action_type: action }
                : evidenceResult,
          ),
        ),
      ),
    );
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    render(
      <EvidenceExplorer
        datasetId={sample.dataset_id}
        onDataChanged={vi.fn()}
        onOpenReceipt={vi.fn()}
      />,
    );
    await user.click(
      await screen.findByRole("checkbox", {
        name: `Select ${sample.filename}`,
      }),
    );
    await user.click(screen.getByRole("button", { name: label }));
    expect(
      await screen.findByRole("region", { name: "Receipt" }),
    ).toBeVisible();
    expect(fetch).toHaveBeenCalledWith(
      `/api/actions/${action}/prepare`,
      expect.objectContaining<Record<string, unknown>>({
        body: expect.stringContaining('"version_ids":["source-1"]'),
      }),
    );
    expect(fetch).toHaveBeenCalledWith(
      `/api/actions/${actionPlan.id}/execute`,
      expect.objectContaining<Record<string, unknown>>({
        body: expect.stringContaining('"operation_id":"operation-1"'),
      }),
    );
  },
);
it("prepares deletion in the existing approval card without issuing execute", async () => {
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(path.endsWith("/prepare") ? actionPlan : evidenceResult),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <EvidenceExplorer
      datasetId={sample.dataset_id}
      onDataChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(
    await screen.findByRole("checkbox", { name: `Select ${sample.filename}` }),
  );
  await user.click(screen.getByRole("button", { name: "Delete selection" }));
  expect(
    await screen.findByRole("button", { name: "Approve and delete files" }),
  ).toBeVisible();
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
});
it("turns cursor pages without retaining stale checked assets", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({ ...evidenceResult, next_cursor: "image-1", total: 2 }),
      ),
    )
    .mockResolvedValue(
      new Response(
        JSON.stringify({
          ...evidenceResult,
          items: [
            {
              ...sample,
              asset_ref: { ...sample.asset_ref, asset_id: "image-2" },
              filename: "val/next.png",
            },
          ],
        }),
      ),
    );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <EvidenceExplorer
      datasetId={sample.dataset_id}
      onDataChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(
    await screen.findByRole("checkbox", { name: `Select ${sample.filename}` }),
  );
  await user.click(screen.getByRole("button", { name: "Next page" }));
  await waitFor(() => {
    expect(screen.getByText("Page 2")).toBeVisible();
  });
  expect(screen.getByRole("button", { name: "Create version" })).toBeDisabled();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/evidence/query",
    expect.objectContaining<Record<string, unknown>>({
      body: expect.stringContaining('"cursor":"image-1"'),
    }),
  );
});
