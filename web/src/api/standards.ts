import { post } from "./client";

import type { components } from "./generated";
import type { ActionPlan } from "./types";

export type FieldStandard = components["schemas"]["FieldStandard"];
export type CodeList = components["schemas"]["CodeList"];
export type ColumnMapping = components["schemas"]["ColumnMapping"];
export type MappingSuggestion = components["schemas"]["MappingSuggestion"];
export type ColumnProfile = components["schemas"]["ColumnProfile"];
export type StandardsCoverage = components["schemas"]["StandardsCoverage"];
export type StandardsReport = components["schemas"]["StandardsReport"];
export type StandardsHistory = components["schemas"]["StandardsHistory"];

export function standardsPath(
  collection: "fields" | "code-lists",
  search = "",
  status = "",
) {
  const query = new URLSearchParams();
  if (search) query.set("search", search);
  if (status) query.set("status", status);
  return `/api/standards/${collection}${query.size ? `?${query.toString()}` : ""}`;
}
export function standardsReportPath(tableId?: string) {
  return `/api/standards/report${tableId ? `?${new URLSearchParams({ table_id: tableId }).toString()}` : ""}`;
}
export function prepareMapping(mapping: ColumnMapping) {
  return post<ActionPlan>("/api/actions/confirm_standard_mapping/prepare", {
    mapping,
  });
}
export function prepareStandard(definition: FieldStandard) {
  return post<ActionPlan>("/api/actions/update_standard/prepare", {
    definition,
  });
}
export function prepareCodeList(definition: CodeList) {
  return post<ActionPlan>("/api/actions/update_code_list/prepare", {
    definition,
  });
}
