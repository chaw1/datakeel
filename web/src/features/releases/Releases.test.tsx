import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";
import { dataset, version } from "../../test/fixtures";

import { Releases } from "./Releases";

const summary = {
  annotation_count: 2,
  label_count: 1,
  quality_score: 90,
  evidence_decisions: {},
};
const release = {
  id: "release-1",
  dataset_id: dataset.id,
  version_id: version.id,
  tag: "v1.2.0",
  notes: "Reviewed release",
  created_at: 1700000000,
  manifest_sha256: "f".repeat(64),
  file_count: 1,
  total_bytes: 120,
  metadata: {},
  summary,
};
const categories = [
  "file_count",
  "bytes",
  "hashes",
  "annotations",
  "metadata",
  "lineage",
] as const;
const report = {
  id: "report-1",
  release_id: release.id,
  created_at: 1700000000,
  passed: false,
  categories: categories.map((name) => ({
    name,
    passed: name !== "hashes",
    differences:
      name === "hashes"
        ? [
            {
              path: "files/sample.txt",
              expected: "original",
              actual: "changed",
              reason: "Content hash differs",
            },
          ]
        : [],
  })),
};

it("prepares a frozen release and requires explicit approval before executing", async () => {
  let published = false;
  const fetch = vi.fn((path: string) => {
    let payload: unknown = [];
    if (path.endsWith("/prepare") || path.startsWith("/api/approvals/"))
      payload = { ...actionPlan, action_type: "publish_release" };
    if (path.endsWith("/execute")) {
      published = true;
      payload = { ...actionRun, action_type: "publish_release" };
    }
    if (path.endsWith("/releases")) payload = published ? [release] : [];
    return Promise.resolve(new Response(JSON.stringify(payload)));
  });
  vi.stubGlobal("fetch", fetch);
  const changed = vi.fn();
  const user = userEvent.setup();
  render(
    <Releases
      versions={[version]}
      datasetId={dataset.id}
      onChanged={changed}
    />,
  );
  await user.click(screen.getByText("Publish a release"));
  await user.type(screen.getByLabelText("Semantic version tag"), "v1.2.0");
  await user.type(screen.getByLabelText("Release notes"), release.notes);
  await user.click(screen.getByRole("button", { name: "Review release plan" }));
  const approve = await screen.findByRole("button", {
    name: "Approve and publish release",
  });
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/publish_release/prepare",
    expect.objectContaining({
      body: JSON.stringify({
        dataset_id: dataset.id,
        version_id: version.id,
        tag: release.tag,
        notes: release.notes,
      }),
    }),
  );
  await user.click(approve);
  expect(
    await screen.findByRole("button", { name: release.tag }),
  ).toBeVisible();
  expect(
    fetch.mock.calls.findIndex(([path]) => path.startsWith("/api/approvals/")),
  ).toBeLessThan(
    fetch.mock.calls.findIndex(([path]) => path.endsWith("/execute")),
  );
  expect(changed).toHaveBeenCalledOnce();
});

it("requests an explicit release budget only when the user enters one", async () => {
  const fetch = vi.fn((path: string) => {
    let payload: unknown = [];
    if (path.includes("/prepare"))
      payload = { ...actionPlan, action_type: "publish_release" };
    return Promise.resolve(new Response(JSON.stringify(payload)));
  });
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <Releases
      versions={[version]}
      datasetId={dataset.id}
      onChanged={vi.fn()}
    />,
  );
  await user.click(screen.getByText("Publish a release"));
  await user.type(screen.getByLabelText("Semantic version tag"), "1.0.0");
  await user.type(screen.getByLabelText("Maximum files"), "20000");
  await user.type(screen.getByLabelText("Maximum size (GiB)"), "2");
  await user.click(screen.getByRole("button", { name: "Review release plan" }));
  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      `/api/actions/publish_release/prepare?max_objects=20000&max_bytes=${String(2 * 1024 ** 3)}`,
      expect.anything(),
    );
  });
});

it("loads release details and archived six-category differences and persists a new check", async () => {
  let reports = [report];
  const fetch = vi.fn((path: string) => {
    let payload: unknown = [release];
    if (path === `/api/releases/${release.id}`) payload = release;
    if (path.includes("/files?")) payload = { files: [], next_offset: null };
    if (path.endsWith("/reconciliations")) payload = reports;
    if (path.endsWith("/reconcile")) {
      reports = [
        {
          ...report,
          id: "report-2",
          passed: true,
          categories: categories.map((name) => ({
            name,
            passed: true,
            differences: [],
          })),
        },
      ];
      payload = reports[0];
    }
    return Promise.resolve(new Response(JSON.stringify(payload)));
  });
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<Releases versions={[version]} datasetId={dataset.id} />);
  await user.click(await screen.findByRole("button", { name: release.tag }));
  expect(await screen.findByText(release.manifest_sha256)).toBeVisible();
  expect(await screen.findByText("Content hash differs")).toBeVisible();
  for (const label of [
    "File count",
    "Total and per-file bytes",
    "Content hashes",
    "Annotation and label counts",
    "Required metadata fields and values",
    "Lineage references",
  ]) {
    expect(
      screen.getByRole("heading", { name: new RegExp(`^${label} ·`) }),
    ).toBeVisible();
  }
  await user.click(
    screen.getByRole("button", { name: "Reconcile stored objects" }),
  );
  await waitFor(() => {
    expect(screen.queryByText("Content hash differs")).not.toBeInTheDocument();
  });
  expect(fetch).toHaveBeenCalledWith(
    `/api/releases/${release.id}/reconcile`,
    expect.objectContaining({ method: "POST" }),
  );
  expect(
    fetch.mock.calls.filter(([path]) => path.endsWith("/reconciliations")),
  ).toHaveLength(2);
});
