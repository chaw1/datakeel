import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { AnnotationQuality } from "./AnnotationQuality";

import type {
  AnnotationOverview,
  AnnotationReport,
} from "../../api/annotation";

const estimate = { value: 0.4, observed_agreement: 0.7, sample_count: 50 };

const report: AnnotationReport = {
  id: "batch-2",
  dataset_id: "dataset-1",
  version_id: "version-1",
  name: "Reworked panel",
  batch_digest: "digest",
  sample_count: 50,
  annotation_count: 100,
  created_at: "2026-10-27T00:00:00Z",
  rework_of: "batch-1",
  result: {
    sample_count: 50,
    annotator_count: 2,
    classification: {
      fleiss_kappa: estimate,
      krippendorff_alpha: { ...estimate, value: 0.406 },
      pairs: [
        {
          annotator_a: "amber",
          annotator_b: "cobalt",
          cohen_kappa: estimate,
          confusion: [],
          categories: ["no", "yes"],
          matrix: [
            [15, 10],
            [5, 20],
          ],
        },
      ],
    },
    boxes: [],
    spans: [],
    findings: [
      {
        finding_id: "f1",
        sample_id: "file-7",
        annotator_id: "cobalt",
        code: "bbox_missing",
        reason: "A box drawn by a strict majority of the panel is absent here",
        evidence: ["support=2/3"],
        related_sample_ids: [],
      },
    ],
  },
  comparison: {
    before_count: 4,
    after_count: 1,
    corrected_count: 3,
    introduced_count: 1,
    remaining_count: 0,
    unassessed_count: 0,
    changed_records: 6,
    unchanged_records: 94,
    added_records: 0,
    removed_records: 0,
    inspection_defects: 2,
    inspection_defects_changed: 2,
    corrected: [],
    introduced: [],
    remaining: [],
    unassessed: [],
  },
};

const overview: AnnotationOverview = {
  dataset_id: "dataset-1",
  version_id: null,
  latest: report,
  batches: [report],
  inspections: [],
  sampling_plans: [],
};

function serve() {
  const fetch = vi.fn((path: string, init: RequestInit) => {
    if (init.method === "POST") return Promise.resolve(new Response("{}"));
    expect(path).toBe("/api/datasets/dataset-1/annotation-quality");
    return Promise.resolve(new Response(JSON.stringify(overview)));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

it("shows agreement, the nominal confusion matrix, findings and rework counts", async () => {
  serve();
  render(<AnnotationQuality datasetId="dataset-1" />);
  expect(await screen.findByText("Fleiss’ κ")).toBeVisible();
  expect(screen.getAllByText("0.4000").length).toBeGreaterThan(0);
  const matrix = screen.getByText("amber \\ cobalt").closest("table");
  expect(matrix).not.toBeNull();
  expect(within(matrix as HTMLElement).getByText("15")).toBeInTheDocument();
  expect(screen.getByText("Box missed by this annotator")).toBeVisible();
  expect(screen.getByText("Inspection defects changed")).toBeVisible();
  expect(screen.getByText("2 / 2")).toBeVisible();
});

it("draws an AQL sample without ratio overrides", async () => {
  const fetch = serve();
  render(<AnnotationQuality datasetId="dataset-1" />);
  fireEvent.click(await screen.findByText("Draw reproducible sample"));
  await vi.waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/datasets/dataset-1/annotation-quality/samples",
      expect.objectContaining({ method: "POST" }),
    );
  });
  const post = fetch.mock.calls.find(([, init]) => init.method === "POST");
  const body = post?.[1].body;
  expect(typeof body).toBe("string");
  expect(JSON.parse(body as string)).toEqual({
    batch_id: "batch-2",
    method: "aql",
    seed: 42,
    aql: 2.5,
  });
});
