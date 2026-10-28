import { describe, expect, it } from "vitest";

import { file, imageFile, version } from "../../test/fixtures";

import {
  evidenceSource,
  extractionInput,
  supportsEvidence,
} from "./extraction";

const image = {
  ...imageFile,
  metadata: {
    evidence_sample: { sample_key: "train/scene/image.png", split: "train" },
  },
};
const paired = { ...version, manifest: [image] };

it("pins evidence's source version instead of picking a newer derived version", () => {
  const latest = {
    ...paired,
    id: "newer",
    created_at: version.created_at + 10,
  };
  expect(evidenceSource([latest, paired], paired.id)).toBe(paired);
  expect(evidenceSource([latest, paired], "missing")).toBeUndefined();
});

it("matches original manifest ordering including deterministic timestamp ties", () => {
  const earlier = { ...paired, id: "source-a" };
  const tied = { ...paired, id: "source-b" };
  const later = { ...paired, id: "later", created_at: version.created_at + 1 };
  const input = [later, tied, earlier];
  expect(evidenceSource(input)).toBe(earlier);
  expect(input).toEqual([later, tied, earlier]);
  expect(evidenceSource([])).toBeUndefined();
});

it("keeps missing sidecars valid so extraction can produce unknown evidence", () => {
  expect(supportsEvidence(paired)).toBe(true);
  expect(
    supportsEvidence({
      ...paired,
      manifest: [
        {
          ...image,
          metadata: {
            evidence_sample: {
              sample_key: "val/a.png",
              split: "val",
              caption: null,
              annotation: null,
            },
          },
        },
        file,
      ],
    }),
  ).toBe(true);
});

describe("paired source eligibility", () => {
  it.each([
    undefined,
    {},
    { sample_key: "", split: "train" },
    { sample_key: "image.png", split: "holdout" },
    { sample_key: "image.png", split: "train", caption: "caption.txt" },
    { sample_key: "image.png", split: "train", annotation: {} },
  ])("rejects malformed sample metadata %j", (evidence_sample) => {
    expect(
      supportsEvidence({
        ...paired,
        manifest: [{ ...image, metadata: { evidence_sample } }],
      }),
    ).toBe(false);
  });
  it("requires every routed image to be paired and at least one image", () => {
    expect(supportsEvidence(version)).toBe(false);
    expect(supportsEvidence({ ...paired, manifest: [image, imageFile] })).toBe(
      false,
    );
    expect(supportsEvidence({ ...paired, manifest: [] })).toBe(false);
  });
});

it.each(["train", "val", "test"])(
  "accepts paired images from the %s split",
  (split) => {
    expect(
      supportsEvidence({
        ...paired,
        manifest: [
          {
            ...image,
            metadata: {
              evidence_sample: {
                sample_key: `${split}/scene/image.png`,
                split,
                caption: null,
                annotation: null,
              },
            },
          },
        ],
      }),
    ).toBe(true);
  },
);

it("sends the explicit five-extractor chain with one global near-duplicate shard", () => {
  const input = extractionInput("dataset-id", "source-version");
  expect(input).toMatchObject({
    dataset_id: "dataset-id",
    version_id: "source-version",
    shards: 1,
    queue: "cpu",
  });
  expect(input.pipeline).toEqual({
    max_workers: 1,
    outputs: ["near_duplicate.files"],
    nodes: [
      {
        id: "evidence_images",
        kind: "route",
        inputs: { files: "$input.files" },
        params: {},
      },
      {
        id: "image_phash",
        kind: "operator",
        operator: "evidence.image_phash",
        inputs: { files: "evidence_images.image" },
        params: { extractor_version: "1.0" },
      },
      {
        id: "caption_mentions",
        kind: "operator",
        operator: "evidence.caption_mentions",
        inputs: { files: "image_phash.files" },
        params: { extractor_version: "1.0" },
      },
      {
        id: "annotation_labels",
        kind: "operator",
        operator: "evidence.annotation_labels",
        inputs: { files: "caption_mentions.files" },
        params: { extractor_version: "1.0" },
      },
      {
        id: "label_gap",
        kind: "operator",
        operator: "evidence.label_gap",
        inputs: { files: "annotation_labels.files" },
        params: { extractor_version: "1.0" },
      },
      {
        id: "near_duplicate",
        kind: "operator",
        operator: "evidence.near_duplicate",
        inputs: { files: "label_gap.files" },
        params: { extractor_version: "1.0" },
      },
    ],
  });
});
