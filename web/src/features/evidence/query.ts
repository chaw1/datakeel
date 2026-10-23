import type { components } from "../../api/generated";
import type { EvidenceQuery, EvidenceSample } from "../../api/types";

export type EvidenceFilters = {
  concept: string;
  presence: "present" | "absent" | "unknown";
  scene: string;
  sceneState: "present" | "absent" | "unknown";
  gap: "" | "missing" | "present" | "unknown";
  near: "" | "train" | "val";
  split: "" | "train" | "val";
  qualityMin: number;
  qualityMax: number;
  sort: "review" | "filename" | "quality";
};
export const initialFilters: EvidenceFilters = {
  concept: "",
  presence: "present",
  scene: "",
  sceneState: "present",
  gap: "",
  near: "",
  split: "",
  qualityMin: 0,
  qualityMax: 100,
  sort: "review",
};
export const exampleFilters: EvidenceFilters = {
  ...initialFilters,
  concept: "person",
  gap: "missing",
  split: "val",
  near: "train",
};

export function evidenceQuery(
  datasetId: string,
  filters: EvidenceFilters,
  cursor: string | null,
): EvidenceQuery {
  const rules: NonNullable<EvidenceQuery["assertion_filters"]> = [];
  for (const [concept, value] of [
    [filters.concept, filters.presence],
    [filters.scene, filters.sceneState],
  ] as const) {
    if (concept)
      rules.push({ predicate: "mentions", concept, value, operator: "exists" });
  }
  if (filters.gap)
    rules.push({
      predicate: filters.gap === "missing" ? "annotated_as" : "label_gap",
      concept: filters.concept || "person",
      value: filters.gap === "unknown" ? "unknown" : "present",
      operator: filters.gap === "missing" ? "not_exists" : "exists",
    });
  return {
    schema_version: "1.1",
    object_type: "file",
    namespace: "default",
    include_deleted: false,
    dataset_id: datasetId,
    assertion_filters: rules,
    split: filters.split || null,
    has_near_duplicate_in: filters.near || null,
    quality_min: filters.qualityMin,
    quality_max: filters.qualityMax,
    cursor,
    page_size: 20,
    limit: 1000,
    sort: filters.sort,
  };
}

export function exactSelection(
  samples: EvidenceSample[],
): components["schemas"]["ObjectSet"] | null {
  const first = samples.at(0);
  if (
    !first ||
    samples.some(
      (sample) =>
        sample.dataset_id !== first.dataset_id ||
        sample.source_version !== first.source_version ||
        sample.deleted,
    )
  )
    return null;
  return {
    schema_version: "1.1",
    object_type: "file",
    namespace: "default",
    include_deleted: false,
    dataset_id: first.dataset_id,
    version_ids: [first.source_version],
    limit: samples.length,
    filters: [
      {
        field: "id",
        operator: "in",
        value: samples.map((sample) => sample.asset_ref.asset_id),
      },
    ],
  };
}
