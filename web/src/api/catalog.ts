import { post } from "./client";

import type { components } from "./generated";
import type { ActionPlan } from "./types";

export type CatalogObject = components["schemas"]["CatalogObject"];
export type CatalogPage = components["schemas"]["CatalogPage"];
export type CatalogTableDetail = components["schemas"]["CatalogTableDetail"];
export type ImpactResult = components["schemas"]["ImpactResult"];
export type MetricCard = components["schemas"]["MetricCard"];
export type MetricDefinition = components["schemas"]["MetricDefinition"];
export type MetricFilter = components["schemas"]["MetricFilter"];
export type CatalogCollection =
  "sources" | "tables" | "columns" | "metrics" | "terms";

export function catalogPath(
  collection: CatalogCollection,
  offset = 0,
  search = "",
  parentId?: string,
) {
  const query = new URLSearchParams({ limit: "20", offset: String(offset) });
  if (search) query.set("search", search);
  if (parentId) query.set("parent_id", parentId);
  return `/api/catalog/${collection}?${query.toString()}`;
}

export function tablePath(id: string) {
  return `/api/catalog/tables/${encodeURIComponent(id)}`;
}

export function metricPath(id: string) {
  return `/api/catalog/metrics/${encodeURIComponent(id)}`;
}

export function impactPath(id: string) {
  return `/api/catalog/impact?${new URLSearchParams({ asset_id: id, max_nodes: "100" }).toString()}`;
}

export function prepareMetric(definition: MetricDefinition) {
  return post<ActionPlan>("/api/actions/update_metric/prepare", { definition });
}
