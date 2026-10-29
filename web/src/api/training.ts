import { post } from "./client";

import type { components } from "./generated";
import type { ActionPlan } from "./types";

export type SplitSet = components["schemas"]["SplitSet"];
export type SplitRequest = components["schemas"]["SplitRequest"];
export type LeakageReport = components["schemas"]["LeakageReport"];

export function trainingPath(datasetId: string, versionId: string) {
  return `/api/datasets/${encodeURIComponent(datasetId)}/versions/${encodeURIComponent(versionId)}/training`;
}

export function createSplit(
  datasetId: string,
  versionId: string,
  request: SplitRequest,
  preview: boolean,
) {
  return post<SplitSet>(
    `${trainingPath(datasetId, versionId)}/${preview ? "preview" : "splits"}`,
    request,
  );
}

export function exportTraining(
  split: SplitSet,
  format: string,
  destination: string,
  annotatorId: string,
) {
  return post<ActionPlan>("/api/actions/export_dataset/prepare", {
    dataset_id: split.dataset_id,
    version_id: split.version_id,
    split_set_id: split.id,
    format,
    destination,
    ...(annotatorId ? { annotator_id: annotatorId } : {}),
  });
}
