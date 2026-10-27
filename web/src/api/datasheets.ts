import { get, post } from "./client";

import type { components } from "./generated";
import type { ActionPlan } from "./types";

export type DatasheetDocument = components["schemas"]["DatasheetDocument"];
export type DatasheetFact = components["schemas"]["DatasheetFact"];
type GenerationRequest = components["schemas"]["GenerateDatasheetRequest"];

export function listDatasheets(datasetId: string) {
  return get<DatasheetDocument[]>(
    `/api/datasets/${encodeURIComponent(datasetId)}/datasheets`,
  );
}

export function generateDatasheet(
  datasetId: string,
  versionId: string,
  language: DatasheetDocument["language"],
  mode: DatasheetDocument["mode"],
  modelOptions: { provider: "fake" | "openai" | "anthropic"; model: string },
) {
  const body = {
    version_id: versionId,
    language,
    mode,
    ...(mode === "model" ? modelOptions : {}),
  } satisfies Partial<GenerationRequest> &
    Pick<GenerationRequest, "version_id" | "language" | "mode">;
  return post<ActionPlan>(
    `/api/datasets/${encodeURIComponent(datasetId)}/datasheets`,
    body,
  );
}

export function publishDatasheet(id: string) {
  return post<ActionPlan>(
    `/api/datasheets/${encodeURIComponent(id)}/publish`,
    {},
  );
}

export function datasheetDownload(id: string, format: "markdown" | "html") {
  return `/api/datasheets/${encodeURIComponent(id)}/download?format=${format}`;
}
