import {
  explanation,
  kgAnchor,
  kgPlan,
  kgRun,
  relation,
  sourceText,
} from "./kgFixtures";

import type { KGExplanation, KGRun } from "../api/kg";
import type { ActionPlan, Assertion } from "../api/types";

const report = kgRun.report;
const estimate = kgPlan.impact.kg_estimate;
if (!report || !estimate)
  throw new Error("Missing graph fixture report or estimate");

export const imageRef = {
  asset_id: "image-1",
  asset_type: "file",
  namespace: "default",
  version: "image-version",
};
export const transcriptRef = {
  ...imageRef,
  asset_id: "transcript-1",
  asset_type: "image_transcript",
  version: "b".repeat(64),
};
export const imageRegions: Assertion["anchors"] = [
  [10, 10, 90, 30],
  [110, 50, 190, 80],
].map((bbox) => ({
  ...kgAnchor(0, 1),
  asset_ref: imageRef,
  selector: {
    type: "image_region",
    bbox: [bbox[0], bbox[1], bbox[2], bbox[3]],
    width: 200,
    height: 100,
  },
}));
export const imageExplanation: KGExplanation = {
  ...explanation,
  relation: {
    ...relation,
    transcriber: "replay",
    transcription_model: "recorded-vision-model",
    transcription_profile_id: "replay-image-demo",
    image_located: true,
    assertion: {
      ...relation.assertion,
      anchors: [
        ...relation.assertion.anchors.map((anchor) => ({
          ...anchor,
          asset_ref: transcriptRef,
        })),
        ...imageRegions,
      ],
      verification_detail: {
        ...relation.assertion.verification_detail,
        issues: [],
        locations: [
          {
            source: transcriptRef,
            evidence: { type: "text_span", start: 7, end: 27 },
            head: { type: "text_span", start: 7, end: 12 },
            tail: { type: "text_span", start: 22, end: 26 },
            issues: [],
          },
        ],
      },
    },
  },
  sources: [
    {
      asset_ref: imageRef,
      filename: "diagram.png",
      text: "",
      image_url: "/api/kg/sources/image-1/image?version_id=image-version",
      width: 200,
      height: 100,
    },
    {
      asset_ref: transcriptRef,
      filename: "diagram.png transcript",
      text: sourceText,
      transcriber: "replay",
      transcription_model: "recorded-vision-model",
    },
  ],
};
export const imageRun: KGRun = {
  ...kgRun,
  report: {
    ...report,
    located_relations: 5,
    unlocated_relations: 1,
    transcription_failed: 1,
    cloud_calls: 0,
    cloud_cost_usd: "0",
    transcriptions: [
      {
        external: false,
        reasons: [],
        quality_issues: [],
        ignored_field_count: 0,
        file_id: "image-1",
        filename: "diagram.png",
        backend: "replay",
        mode: "vlm",
        model: "recorded-vision-model",
        cached: true,
        status: "completed",
      },
      {
        external: false,
        reasons: [],
        quality_issues: ["truncated"],
        ignored_field_count: 0,
        file_id: "image-2",
        filename: "scripted-truncated.png",
        backend: "fake",
        mode: "ocr",
        model: "scripted-truncation",
        cached: false,
        status: "failed",
        error: "truncated",
      },
    ],
  },
};
export const imagePlan: ActionPlan = {
  ...kgPlan,
  impact: {
    ...kgPlan.impact,
    kg_estimate: {
      ...estimate,
      extraction_input_basis: "transcription_limit",
    },
    transcription_estimate: {
      target_host: "vision.example.com",
      auto_images: 0,
      possible_external_images: [],
      model: "vision-model",
      images: 2,
      image_tokens: 260,
      max_output_tokens: 4096,
      cost_upper_usd: null,
    },
  },
};
