import { expect, it } from "vitest";

import { sample } from "../../test/evidenceFixtures";

import { evidenceQuery, exactSelection, exampleFilters } from "./query";

it("builds the canonical val/person/missing-annotation/train-neighbor query", () => {
  expect(evidenceQuery("dataset", exampleFilters, null)).toMatchObject({
    schema_version: "1.1",
    sort: "review",
    split: "val",
    has_near_duplicate_in: "train",
    assertion_filters: [
      {
        predicate: "mentions",
        concept: "person",
        value: "present",
        operator: "exists",
      },
      {
        predicate: "annotated_as",
        concept: "person",
        value: "present",
        operator: "not_exists",
      },
    ],
  });
});
it("keeps scene and caption states separate and preserves the quality interval", () => {
  expect(
    evidenceQuery(
      "dataset",
      {
        ...exampleFilters,
        presence: "unknown",
        scene: "night",
        sceneState: "absent",
        gap: "unknown",
        qualityMin: 10,
        qualityMax: 80,
      },
      "last-image",
    ),
  ).toMatchObject({
    cursor: "last-image",
    quality_min: 10,
    quality_max: 80,
    assertion_filters: [
      { predicate: "mentions", concept: "person", value: "unknown" },
      { predicate: "mentions", concept: "night", value: "absent" },
      { predicate: "label_gap", concept: "person", value: "unknown" },
    ],
  });
});
it("pins checked identities to exactly one dataset and source version", () => {
  expect(exactSelection([sample])).toMatchObject({
    dataset_id: sample.dataset_id,
    version_ids: [sample.source_version],
    limit: 1,
    filters: [
      { field: "id", operator: "in", value: [sample.asset_ref.asset_id] },
    ],
  });
  expect(exactSelection([])).toBeNull();
  expect(
    exactSelection([sample, { ...sample, source_version: "other" }]),
  ).toBeNull();
  expect(
    exactSelection([sample, { ...sample, dataset_id: "other" }]),
  ).toBeNull();
  expect(exactSelection([{ ...sample, deleted: true }])).toBeNull();
});

it("preserves test membership and test-neighbor predicates in the API request", () => {
  expect(
    evidenceQuery(
      "dataset",
      { ...exampleFilters, split: "test", near: "test" },
      null,
    ),
  ).toMatchObject({ split: "test", has_near_duplicate_in: "test" });
});
