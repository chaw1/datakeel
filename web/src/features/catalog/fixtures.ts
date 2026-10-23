import { vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";

import type {
  CatalogObject,
  CatalogPage,
  CatalogTableDetail,
  ImpactResult,
  MetricCard,
} from "../../api/catalog";

export const source: CatalogObject = {
  asset_ref: {
    namespace: "default",
    asset_type: "source",
    asset_id: "ecommerce",
  },
  name: "Fictional Kitchen Ecommerce",
  revision: 1,
  properties: { dialect: "sqlite" },
};
export const table: CatalogObject = {
  asset_ref: {
    namespace: "default",
    asset_type: "table",
    asset_id: "ecommerce/main/orders",
  },
  name: "orders",
  revision: 1,
  source_id: "ecommerce",
  schema_name: "main",
  properties: {},
};
export const column: CatalogObject = {
  asset_ref: {
    namespace: "default",
    asset_type: "column",
    asset_id: "ecommerce/main/orders/paid_amount",
  },
  name: "paid_amount",
  revision: 1,
  source_id: "ecommerce",
  table_id: table.asset_ref.asset_id,
  properties: { data_type: "INTEGER", nullable: false, primary_key: false },
};
export const metric: MetricCard = {
  status: "resolved",
  reasons: [],
  definition: {
    id: "retail_revenue",
    name: "Retail revenue",
    owner: "Retail team",
    version: 1,
    description: "Completed orders at the paid price.",
    caveats: ["Synthetic amounts in yuan."],
    synonyms: ["Retail receipts"],
    dimensions: ["retail_region"],
    measure: {
      table: table.asset_ref.asset_id,
      column: column.asset_ref.asset_id,
      aggregation: "sum",
    },
    time: { column: `${table.asset_ref.asset_id}/date`, granularity: "day" },
    filters: [
      {
        column: `${table.asset_ref.asset_id}/status`,
        op: "eq",
        value: "completed",
      },
    ],
  },
};
export const metricObject: CatalogObject = {
  asset_ref: {
    namespace: "default",
    asset_type: "metric",
    asset_id: metric.definition.id,
    version: "1",
  },
  name: metric.definition.name,
  revision: 1,
  properties: { ...metric },
};
export const term: CatalogObject = {
  asset_ref: {
    namespace: "default",
    asset_type: "term",
    asset_id: "term/Retail",
  },
  name: "Retail",
  revision: 1,
  properties: {
    synonyms: ["Retail receipts"],
    means: { kind: "metric", id: "retail_revenue" },
  },
};
export const impact: ImpactResult = {
  asset_id: column.asset_ref.asset_id,
  objects: [column, table, metricObject, term],
  truncated: false,
  links: [
    { source: table.asset_ref, target: column.asset_ref, kind: "contains" },
    {
      source: metricObject.asset_ref,
      target: column.asset_ref,
      kind: "measures",
    },
    { source: term.asset_ref, target: metricObject.asset_ref, kind: "means" },
  ],
};
export const detail: CatalogTableDetail = {
  table,
  columns: [
    column,
    {
      ...column,
      name: "list_amount",
      asset_ref: {
        namespace: "default",
        asset_type: "column",
        asset_id: `${table.asset_ref.asset_id}/list_amount`,
      },
    },
  ],
  owners: [],
  metrics: [metricObject],
  neighbors: impact,
};
export const metricPlan = {
  ...actionPlan,
  action_type: "update_metric" as const,
  reversible: true,
  canonical_params: { definition: metric.definition },
};
export const metricRun = {
  ...actionRun,
  action_type: "update_metric" as const,
};

export function page(
  items: CatalogObject[],
  total = items.length,
  offset = 0,
): CatalogPage {
  return { items, total, offset, limit: 20 };
}

export function mockCatalogFetch() {
  const fetch = vi.fn<(input: string, init?: RequestInit) => Promise<Response>>(
    (input) => {
      const url = new URL(input, "http://localhost");
      let payload: unknown = page([]);
      if (url.pathname === "/api/catalog/sources") payload = page([source]);
      if (url.pathname === "/api/catalog/tables") payload = page([table]);
      if (url.pathname.startsWith("/api/catalog/tables/")) payload = detail;
      if (url.pathname === "/api/catalog/metrics")
        payload = page([metricObject]);
      if (url.pathname.startsWith("/api/catalog/metrics/")) payload = metric;
      if (url.pathname === "/api/catalog/terms") payload = page([term]);
      if (url.pathname === "/api/catalog/impact") payload = impact;
      if (url.pathname.endsWith("/prepare")) payload = metricPlan;
      if (url.pathname.endsWith("/execute")) payload = metricRun;
      return Promise.resolve(new Response(JSON.stringify(payload)));
    },
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
