import { post } from "./client";

import type { components } from "./generated";

export type AnnotationOverview =
  components["schemas"]["AnnotationQualityOverview"];
export type AnnotationReport = components["schemas"]["AnnotationQualityReport"];
export type AnnotationResult = components["schemas"]["AnnotationQAResult"];
export type AnnotationBatch = components["schemas"]["AnnotationBatch"];
export type SamplingPlan = components["schemas"]["SamplingPlan"];
export type SamplingRequest = components["schemas"]["SamplingRequest"];
export type InspectionCheck = components["schemas"]["InspectionCheck"];

export function annotationPath(datasetId: string, versionId?: string) {
  const base = `/api/datasets/${encodeURIComponent(datasetId)}/annotation-quality`;
  return versionId
    ? `${base}?version_id=${encodeURIComponent(versionId)}`
    : base;
}

export function createSample(datasetId: string, request: SamplingRequest) {
  return post<SamplingPlan>(`${annotationPath(datasetId)}/samples`, request);
}

export function importAnnotationBatch(
  datasetId: string,
  body: components["schemas"]["AnnotationImportRequest"],
) {
  return post<AnnotationReport>(`${annotationPath(datasetId)}/batches`, body);
}
