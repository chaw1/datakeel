import { post } from "./client";

import type { components } from "./generated";

export type MetadataImportReport =
  components["schemas"]["MetadataImportReport"];
export type DbtImportRequest = components["schemas"]["DbtImportRequest"];
export type AirflowImportRequest =
  components["schemas"]["AirflowImportRequest"];

export function importDbt(request: DbtImportRequest) {
  return post<MetadataImportReport>("/api/catalog/import/dbt", request);
}

export function importAirflow(request: AirflowImportRequest) {
  return post<MetadataImportReport>("/api/catalog/import/airflow", request);
}
