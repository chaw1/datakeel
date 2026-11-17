import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";
import { dataset } from "../../test/fixtures";

import { DeliveryReview } from "./DeliveryReview";
import {
  clean,
  corrected,
  correctedSplit,
  matched,
  original,
  originalSplit,
} from "./deliveryReviewFixtures";

import type { components } from "../../api/generated";
import type { ActionPlan } from "../../api/types";

const selectionPlan: ActionPlan = {
  ...actionPlan,
  id: "correction",
  action_type: "create_version_from_selection",
  reversible: true,
  manifest: {
    ...actionPlan.manifest,
    objects: corrected.manifest.map((file) => ({
      ...actionPlan.manifest.objects[0],
      asset_ref: {
        asset_id: file.id,
        asset_type: "file",
        namespace: "default",
        version: original.id,
      },
      revision: file.sha256,
      properties: {},
      size: file.size,
    })),
  },
};
const publicationPlan: ActionPlan = {
  ...actionPlan,
  action_type: "publish_release",
  id: "publication",
};
const base = `/api/datasets/${dataset.id}`;
const summary = {
  annotation_count: 0,
  label_count: 0,
  quality_score: 0,
  quality_basis: "mean_file_quality" as const,
  evidence_decisions: {},
};
const release: components["schemas"]["ReleaseView"] = {
  id: "release-1",
  dataset_id: dataset.id,
  version_id: corrected.id,
  file_count: corrected.file_count,
  total_bytes: 240,
  created_at: corrected.created_at,
  tag: "v1.0.0",
  notes: "Reviewed",
  manifest_sha256: "a".repeat(64),
  metadata: { delivery_review: { split_id: correctedSplit.id } },
  summary,
};

function success(value: unknown) {
  return Promise.resolve(new Response(JSON.stringify(value)));
}

it("checks imported splits, creates an exact corrected version, and signs the checked delivery", async () => {
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    if (path.endsWith("/training/splits") && init?.method === "POST")
      return success(
        path.includes(corrected.id) ? correctedSplit : originalSplit,
      );
    if (path.includes("/split-1/leakage")) return success(matched);
    if (path.includes("/split-2/leakage")) return success(clean);
    if (path.endsWith("/create_version_from_selection/prepare"))
      return success(selectionPlan);
    if (path.endsWith("/correction/execute"))
      return success({
        ...actionRun,
        action_type: "create_version_from_selection",
        receipt: {
          ...actionRun.receipt,
          outputs: [{ asset_type: "version", asset_id: corrected.id }],
        },
      });
    if (path === `${base}/versions`) return success([original, corrected]);
    if (path.startsWith(`${base}/diff?`))
      return success({
        counts: {
          added: 0,
          removed: 1,
          content_changed: 0,
          metadata_changed: 0,
        },
      });
    if (
      path.endsWith("/publish_release/prepare") ||
      path === "/api/approvals/publication"
    )
      return success(publicationPlan);
    if (path.endsWith("/publication/execute"))
      return success({
        ...actionRun,
        action_type: "publish_release",
        receipt: {
          ...actionRun.receipt,
          outputs: [{ asset_type: "release", asset_id: release.id }],
        },
      });
    if (path === `/api/releases/${release.id}`) return success(release);
    if (path.includes(`/api/releases/${release.id}/files?`))
      return success({ files: [], next_offset: null });
    return success([]);
  });
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<DeliveryReview datasetId={dataset.id} versions={[original]} />);
  const view = within(
    screen.getByRole("region", { name: "Dataset delivery review" }),
  );
  await user.click(view.getByRole("button", { name: "Check imported splits" }));
  expect(await view.findByText("Blocked by cross-split leakage")).toBeVisible();
  expect(
    view.getByRole("img", { name: "train/scene-one.png" }),
  ).toHaveAttribute(
    "src",
    `${base}/files/sample-a/download?version=${original.id}`,
  );
  expect(view.getByRole("img", { name: "val/scene-copy.png" })).toBeVisible();
  expect(
    within(view.getByRole("region", { name: "Leakage report" })).getByText(
      "bridge",
    ),
  ).toBeVisible();
  expect(view.getByText("Label distribution · 2 labels")).toBeVisible();
  expect(
    view.getByText("1 image without a paired annotation file"),
  ).toBeVisible();
  expect(
    view.queryByText("Sign and deliver this candidate"),
  ).not.toBeInTheDocument();

  await user.click(
    view.getByRole("checkbox", {
      name: "Exclude val/scene-copy.png from the corrected version",
    }),
  );
  await user.click(
    view.getByRole("button", { name: "Review corrected version" }),
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/create_version_from_selection/prepare",
    expect.objectContaining({
      body: JSON.stringify({
        selection: {
          schema_version: "1.1",
          object_type: "file",
          namespace: "default",
          include_deleted: false,
          dataset_id: dataset.id,
          version_ids: [original.id],
          filters: [
            { field: "id", operator: "in", value: ["sample-a", "sample-c"] },
          ],
          limit: 2,
        },
      }),
    }),
  );
  await user.click(await view.findByRole("button", { name: "Execute action" }));
  expect(
    await view.findByText(
      "Corrected version created. Check its imported splits to continue.",
    ),
  ).toBeVisible();
  expect(view.getByLabelText("Candidate version")).toHaveValue(corrected.id);
  expect(view.getByLabelText("Baseline version")).toHaveValue(original.id);
  await user.click(view.getByRole("button", { name: "Check imported splits" }));
  expect(await view.findByText("Ready for release review")).toBeVisible();

  await user.click(view.getByText("Sign and deliver this candidate"));
  await user.type(view.getByLabelText("Semantic version tag"), release.tag);
  await user.click(view.getByRole("button", { name: "Review release plan" }));
  const approve = await view.findByRole("button", {
    name: "Approve and publish release",
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/publish_release/prepare",
    expect.objectContaining({
      body: JSON.stringify({
        dataset_id: dataset.id,
        version_id: corrected.id,
        tag: release.tag,
        notes: "",
        delivery_review: {
          split_id: correctedSplit.id,
          baseline_version_id: original.id,
        },
      }),
    }),
  );
  expect(
    fetch.mock.calls.some(([path]) => path === "/api/approvals/publication"),
  ).toBe(false);
  await user.click(approve);
  expect(await view.findByText("Signed delivery review")).toBeVisible();
  expect(
    view.getByRole("button", { name: "Export delivery package" }),
  ).toBeVisible();
  expect(
    view.getByRole("link", { name: "Open signed release receipt" }),
  ).toBeVisible();
});

it("reopens a saved split and keeps a partial selection from becoming a correction plan", async () => {
  const fetch = vi.fn((path: string) => {
    if (path.endsWith("/training/splits")) return success([originalSplit]);
    if (path.endsWith("/leakage")) return success(matched);
    return success([]);
  });
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <DeliveryReview
      datasetId={dataset.id}
      versions={[{ ...original, file_count: 20000 }]}
    />,
  );
  expect(
    await screen.findByText("Blocked by cross-split leakage"),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Refresh leakage check" }),
  ).toBeEnabled();
  await user.click(
    screen.getByRole("checkbox", {
      name: "Exclude val/scene-copy.png from the corrected version",
    }),
  );
  expect(
    screen.getByRole("button", { name: "Review corrected version" }),
  ).toBeDisabled();
  expect(fetch.mock.calls.every(([path]) => !path.endsWith("/prepare"))).toBe(
    true,
  );
});

it("blocks a clean report that checked only part of the candidate", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) => {
      if (path.endsWith("/training/splits")) return success([correctedSplit]);
      if (path.endsWith("/leakage")) return success(clean);
      return success([]);
    }),
  );
  render(
    <DeliveryReview
      datasetId={dataset.id}
      versions={[{ ...original, id: corrected.id }]}
    />,
  );
  expect(
    await screen.findByText("All files must belong to an imported split"),
  ).toBeVisible();
  expect(
    screen.queryByText("Sign and deliver this candidate"),
  ).not.toBeInTheDocument();
});
