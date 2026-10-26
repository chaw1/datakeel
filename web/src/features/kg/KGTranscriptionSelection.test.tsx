import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { kgPlan, kgProfile, kgSchema } from "../../test/kgFixtures";

import { KGExtractionForm } from "./KGExtractionForm";

import type { KGTranscriptionProfile } from "../../api/kg";

const replay: KGTranscriptionProfile = {
  id: "replay-image-demo",
  backend: "replay",
  mode: "vlm",
  model: "recorded-model",
  interface: "openai",
  prompt_version: "image-transcription-v1",
  coordinate_space: "pixel",
  coordinate_min_median_iou: 0.3,
  max_output_tokens: 4096,
  timeout_seconds: 120,
  request_parameters: {},
  ocr_model_version: "rapidocr-3.10.0-defaults",
};

it("requires an explicit profile for unknown images and freezes the user's choice", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(kgPlan))),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <KGExtractionForm
      datasetId="images"
      versionId="v"
      schemas={[kgSchema]}
      profiles={[kgProfile]}
      transcriptionProfiles={[replay]}
      transcriptionSelection={{ image_count: 2, default_profile_id: null }}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(
    screen.getByText("Prepare graph extraction", { selector: "summary" }),
  );
  const button = screen.getByRole("button", {
    name: "Prepare graph extraction",
  });
  expect(screen.getByLabelText("Image transcription profile")).toHaveValue("");
  expect(button).toBeDisabled();
  expect(screen.getByText(/some images have no demo recording/)).toBeVisible();
  await user.click(button);
  expect(fetch).not.toHaveBeenCalled();
  await user.selectOptions(
    screen.getByLabelText("Image transcription profile"),
    replay.id,
  );
  expect(button).toBeEnabled();
  await user.click(button);
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/run_kg_extraction/prepare",
    expect.objectContaining({
      body: JSON.stringify({
        dataset_id: "images",
        version_id: "v",
        schema_id: "business",
        profile_id: "replay-demo",
        transcription_profile_id: replay.id,
      }),
    }),
  );
});

it("defaults to replay only after complete recording coverage is confirmed", async () => {
  const { rerender } = render(
    <KGExtractionForm
      datasetId="images"
      versionId="v"
      schemas={[kgSchema]}
      profiles={[kgProfile]}
      transcriptionProfiles={[replay]}
      selectionPending
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await userEvent
    .setup()
    .click(
      screen.getByText("Prepare graph extraction", { selector: "summary" }),
    );
  expect(
    screen.getByRole("button", { name: "Prepare graph extraction" }),
  ).toBeDisabled();
  rerender(
    <KGExtractionForm
      datasetId="images"
      versionId="v"
      schemas={[kgSchema]}
      profiles={[kgProfile]}
      transcriptionProfiles={[replay]}
      transcriptionSelection={{ image_count: 2, default_profile_id: replay.id }}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Image transcription profile")).toHaveValue(
    replay.id,
  );
  expect(
    screen.getByRole("button", { name: "Prepare graph extraction" }),
  ).toBeEnabled();
});
