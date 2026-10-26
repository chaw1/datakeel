import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { imageFile } from "../../test/fixtures";
import { kgProfile, kgSchema } from "../../test/kgFixtures";
import { imagePlan, imageRun } from "../../test/kgImageFixtures";

import { KGExtractionForm } from "./KGExtractionForm";
import { KGTranscriptionEstimate } from "./KGTranscriptionEstimate";
import { KGTranscriptions } from "./KGTranscriptions";

import type { KGTranscriptionProfile } from "../../api/kg";

const profile: KGTranscriptionProfile = {
  id: "replay-image-auto",
  backend: "replay",
  mode: "auto",
  model: "scripted",
  interface: "openai",
  prompt_version: "image-transcription-v1",
  max_output_tokens: 4096,
  timeout_seconds: 120,
  request_parameters: {},
  ocr_model_version: "rapidocr-3.10.0-defaults",
};

it("freezes auto selection and the higher-priority single-image override", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(imagePlan))),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <KGExtractionForm
      datasetId="images"
      versionId="v"
      schemas={[kgSchema]}
      profiles={[kgProfile]}
      transcriptionProfiles={[profile]}
      imageFiles={[imageFile]}
      transcriptionSelection={{
        image_count: 1,
        default_profile_id: profile.id,
      }}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(
    screen.getByText("Prepare graph extraction", { selector: "summary" }),
  );
  await user.selectOptions(
    screen.getByLabelText("Transcription mode", { exact: true }),
    "auto",
  );
  await user.click(screen.getByText("Per-image mode overrides"));
  await user.selectOptions(
    screen.getByLabelText("Transcription mode: photo.png"),
    "ocr",
  );
  await user.click(
    screen.getByRole("button", { name: "Prepare graph extraction" }),
  );
  expect(fetch).toHaveBeenCalledOnce();
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/run_kg_extraction/prepare",
    expect.objectContaining({
      body: JSON.stringify({
        dataset_id: "images",
        version_id: "v",
        schema_id: "business",
        profile_id: "replay-demo",
        transcription_profile_id: profile.id,
        transcription_mode: "auto",
        mode_overrides: { "file-2": "ocr" },
      }),
    }),
  );
  expect(
    screen.getByLabelText("Transcription mode", { exact: true }),
  ).toBeDisabled();
  expect(screen.getByLabelText("Transcription mode: photo.png")).toBeDisabled();
});

it("shows the conditional outbound list and conservative price upper bound", () => {
  const estimate = imagePlan.impact.transcription_estimate;
  if (!estimate) throw new Error("Missing fixture estimate");
  render(
    <KGTranscriptionEstimate
      plan={{
        ...imagePlan,
        impact: {
          ...imagePlan.impact,
          transcription_estimate: {
            ...estimate,
            auto_images: 1,
            cost_upper_usd: "0.25",
            possible_external_images: [
              {
                file_id: "image-1",
                filename: "diagram.png",
                image_hash: "a".repeat(64),
                mode: "auto",
              },
            ],
          },
        },
      }}
    />,
  );
  expect(
    screen.getByText("Images that may be sent externally").nextElementSibling,
  ).toHaveTextContent("1");
  expect(screen.getByText("$0.250000")).toBeVisible();
  expect(screen.getByRole("listitem")).toHaveTextContent(
    "diagram.png · Auto: may be sent depending on OCR results",
  );
});

it("shows actual route, translated reasons, external status and excluded OCR reference", async () => {
  const report = imageRun.report;
  if (!report) throw new Error("Missing fixture report");
  render(
    <KGTranscriptions
      report={{
        ...report,
        transcription_external_images: 1,
        transcription_cost_upper_usd: "0.25",
        transcriptions: [
          {
            ...report.transcriptions[0],
            cached: false,
            external: true,
            reasons: [
              "low_confidence",
              "structure_diagram",
              "struck_or_greyed_rows",
              "sparse_text",
              "ocr_failed",
            ],
            ocr_reference: { text: "OCR reference only", error: null },
          },
        ],
      }}
    />,
  );
  expect(
    screen.getByText("Approved transcription cost upper bound (USD)")
      .nextElementSibling,
  ).toHaveTextContent("$0.250000");
  const row = screen.getByRole("row", { name: /diagram.png/ });
  expect(within(row).getByText("replay / vlm")).toBeVisible();
  expect(within(row).getByText("Sent externally")).toBeVisible();
  expect(within(row).getByText(/Low OCR confidence/)).toBeVisible();
  expect(within(row).getByText(/Connectors or arrows/)).toBeVisible();
  expect(within(row).getByText(/Struck-through or greyed/)).toBeVisible();
  expect(within(row).getByText(/Text amount does not match/)).toBeVisible();
  expect(within(row).getByText(/OCR failed or returned/)).toBeVisible();
  await userEvent
    .setup()
    .click(
      within(row).getByText("Local OCR reference (excluded from extraction)"),
    );
  expect(screen.getByText("OCR reference only")).toBeVisible();
  expect(
    screen.getByText("Images actually sent externally").nextElementSibling,
  ).toHaveTextContent("1");
});
