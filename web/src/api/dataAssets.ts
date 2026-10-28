import { post } from "./client";

import type { components } from "./generated";
import type { ActionPlan } from "./types";

export type DataAsset = components["schemas"]["DataAsset"];
export type DataAssetCard = components["schemas"]["DataAssetCard"];
export type DataAssetDefinition = components["schemas"]["DataAssetDefinition"];
export type AssetMarketPage = components["schemas"]["AssetMarketPage"];
export type AssetHistory = components["schemas"]["AssetHistory"];
export type AssetApplication = components["schemas"]["AssetApplication"];
export type AssetGrant = components["schemas"]["AssetGrant"];
export type AssetUsage = components["schemas"]["AssetUsage"];
export type AccessScope = AssetApplication["scopes"][number];

export const classifications = [
  ["public", "assetPublic"],
  ["internal", "assetInternal"],
  ["request", "assetRequest"],
  ["restricted", "assetRestricted"],
] as const;
export const assetStatuses = {
  draft: "assetDraft",
  published: "assetPublished",
  withdrawn: "assetWithdrawn",
} as const;
export const scopeLabels = {
  query: "assetScopeQuery",
  export: "assetScopeExport",
  download: "assetScopeDownload",
} as const;
export function assetPath(id: string) {
  return `/api/data-assets/${encodeURIComponent(id)}`;
}
export function prepareAssetAction(action: string, params: unknown) {
  return post<ActionPlan>(`/api/actions/${action}/prepare`, params);
}
