import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan } from "../../test/actionFixtures";
import { dataset, imageFile, version } from "../../test/fixtures";

import { EvidenceExtraction } from "./EvidenceExtraction";
import { extractionInput } from "./extraction";

it("prepares extraction for a pinned source containing test-set paired images", async () => {
  const testSource = {
    ...version,
    id: "test-source",
    manifest: [
      {
        ...imageFile,
        metadata: {
          evidence_sample: {
            sample_key: "test/sample/image.png",
            split: "test",
            caption: null,
            annotation: null,
          },
        },
      },
    ],
  };
  const prepared = {
    ...actionPlan,
    action_type: "run_pipeline",
    reversible: true,
  };
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(path.endsWith("/versions") ? [testSource] : prepared),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <EvidenceExtraction datasetId={dataset.id} sourceVersion={testSource.id} />,
  );
  await user.click(
    await screen.findByRole("button", { name: "Prepare evidence extraction" }),
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/run_pipeline/prepare",
    expect.objectContaining({
      body: JSON.stringify(extractionInput(dataset.id, testSource.id)),
    }),
  );
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
});
