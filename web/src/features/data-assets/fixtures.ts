import { vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";

import type {
  AssetApplication,
  AssetGrant,
  AssetUsage,
  DataAssetCard,
} from "../../api/dataAssets";
import type { ActionPlan } from "../../api/types";

export const assetCard: DataAssetCard = {
  asset: {
    id: "asset-orders",
    revision: 1,
    status: "published",
    created_at: "2026-10-20T00:00:00Z",
    updated_at: "2026-10-21T00:00:00Z",
    definition: {
      target: {
        namespace: "default",
        asset_type: "table",
        asset_id: "commerce/main/orders",
      },
      name: "Orders",
      name_en: "Orders asset",
      description: "Completed synthetic orders at paid price.",
      owner: "Commerce team",
      classification: "request",
      tags: ["retail"],
      synonyms: ["Receipts"],
      scenarios: ["Quarterly reporting"],
      instructions: "Query completed orders only.",
      sample: "order_id, amount\nsample-1, 12",
    },
  },
  quality_score: 94.5,
  quality_trend: [{ occurred_at: "2026-10-20T00:00:00Z", score: 91 }],
  upstream: [
    { namespace: "default", asset_type: "dataset", asset_id: "source-dataset" },
  ],
  downstream: [
    { namespace: "default", asset_type: "metric", asset_id: "retail_revenue" },
  ],
  related_metrics: [
    { namespace: "default", asset_type: "metric", asset_id: "retail_revenue" },
  ],
  updated_at: "2026-10-21T00:00:00Z",
  usage_count: 12,
  user_count: 3,
  downstream_count: 1,
  freshness_seconds: 3600,
  version_release: null,
  standard_coverage: null,
};
export const application: AssetApplication = {
  id: "application-1",
  asset_id: assetCard.asset.id,
  applicant: "local",
  purpose: "Quarterly review",
  scopes: ["query"],
  expires_at: "2099-10-28T00:00:00Z",
  status: "pending",
  created_at: "2026-10-27T00:00:00Z",
  decided_at: null,
  decided_by: null,
  grant_id: null,
};
export const grant: AssetGrant = {
  id: "grant-1",
  application_id: application.id,
  asset_id: assetCard.asset.id,
  subject: "local",
  scopes: ["query"],
  expires_at: "2099-10-28T00:00:00Z",
  created_at: "2026-10-27T00:00:00Z",
  granted_by: "local",
  revoked_at: null,
  revoked_by: null,
};
export const usage: AssetUsage = {
  id: "usage-1",
  asset_id: assetCard.asset.id,
  actor: "local",
  entry: "ask",
  scope: "query",
  occurred_at: "2026-10-27T00:00:00Z",
  grant_id: grant.id,
};
export function mockAssetFetch() {
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    const url = new URL(path, "http://localhost");
    let payload: unknown = {
      items: [assetCard],
      total: 1,
      offset: 0,
      limit: 100,
    };
    if (url.pathname === `/api/data-assets/${assetCard.asset.id}`)
      payload = assetCard;
    if (url.pathname.endsWith("/history"))
      payload = [
        {
          id: "history-1",
          asset_id: assetCard.asset.id,
          operation_id: "operation-1",
          actor: "local",
          action: "publish_data_asset",
          occurred_at: "2026-10-27T00:00:00Z",
          asset: assetCard.asset,
        },
      ];
    if (url.pathname.endsWith("/applications"))
      payload = init?.method === "POST" ? application : [application];
    if (url.pathname.endsWith("/grants")) payload = [grant];
    if (url.pathname.endsWith("/audit")) payload = [usage];
    if (url.pathname.endsWith("/prepare")) {
      const action = url.pathname.split("/")[3] as ActionPlan["action_type"];
      payload = {
        ...actionPlan,
        action_type: action,
        canonical_params: JSON.parse(
          typeof init?.body === "string" ? init.body : "{}",
        ) as unknown,
      };
    }
    if (url.pathname.startsWith("/api/approvals/"))
      payload = { ...actionPlan, status: "APPROVED" };
    if (url.pathname.endsWith("/execute")) payload = actionRun;
    return Promise.resolve(new Response(JSON.stringify(payload)));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
