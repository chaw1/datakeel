import { dataset } from "./fixtures";

import type {
  Assertion,
  EvidenceQueryResult,
  EvidenceSample,
} from "../api/types";

export const evidenceRef = {
  asset_id: "image-1",
  asset_type: "file",
  namespace: "default",
  version: "source-1",
};
export const mention: Assertion = {
  id: "mention-1",
  subject: evidenceRef,
  predicate: "mentions",
  object: { concept: "person", value: "present" },
  status: "candidate",
  schema_version: "1.0",
  producer_event_id: "extract-caption",
  run_id: "extract-run",
  extractor: { id: "evidence.caption_mentions", version: "1.0" },
  anchors: [
    {
      asset_ref: { ...evidenceRef, asset_id: "caption-1" },
      content_revision: "a".repeat(64),
      schema_version: "1.0",
      selector: { type: "text_span", start: 7, end: 13 },
    },
  ],
};
export const annotation: Assertion = {
  ...mention,
  id: "annotation-1",
  predicate: "annotated_as",
  extractor: { id: "evidence.annotation_labels", version: "1.0" },
  producer_event_id: "extract-labels",
  anchors: [
    {
      asset_ref: evidenceRef,
      content_revision: "b".repeat(64),
      schema_version: "1.0",
      selector: {
        type: "image_region",
        bbox: [10, 5, 60, 30],
        width: 100,
        height: 50,
      },
    },
  ],
};
export const sample: EvidenceSample = {
  asset_ref: evidenceRef,
  dataset_id: dataset.id,
  source_version: "source-1",
  filename: "val/example.png",
  split: "val",
  thumbnail_url: `/api/datasets/${dataset.id}/files/image-1/download?version=source-1`,
  caption: "🚶 cafe\u0301 person and car.",
  caption_spans: [{ type: "text_span", start: 7, end: 13 }],
  annotation_boxes: [
    { concept: "person", bbox: [10, 5, 60, 30], width: 100, height: 50 },
  ],
  assertions: [mention, annotation],
  quality_score: 82.5,
  near_duplicates: [
    {
      asset_ref: { ...evidenceRef, asset_id: "image-2" },
      distance: 2,
      reason: "Direct hash pair",
      assertion_id: "pair-1",
    },
  ],
  quarantined: false,
  deleted: false,
  image_width: 100,
  image_height: 50,
};
export const evidenceResult: EvidenceQueryResult = {
  items: [sample],
  next_cursor: null,
  total: 1,
  truncated: false,
};
export const evidenceDataset = {
  ...dataset,
  name: "Paired evidence samples",
  metadata: { evidence_samples: true },
};
