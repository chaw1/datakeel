import { column, detail, metric, table, term } from "../catalog/fixtures";

import { objectData } from "./testFixtures";

import type { components } from "../../api/generated";
import type { ObjectData } from "../../api/objects";
import type { GraphEdge, GraphNode } from "../../api/types";

export const orders = table.asset_ref.asset_id;
const fields = ["paid_amount", "date", "status", "id", "quantity"];
const metrics = ["retail_revenue", "order_count", "retail_units"];
export const summary = "ecommerce/main/retail_summary";
export const paidId = column.asset_ref.asset_id;
const humanNames: Partial<Record<string, string>> = {
  retail_revenue: "Retail revenue",
  order_count: "Order count",
  retail_units: "Retail units",
  retail_region: "Retail region",
  retail_channel: "Retail channel",
  retail_segment: "Retail segment",
};
export const alias = (id: string) => (id === paidId ? "paid-column-node" : id);
export const node = (id: string, asset_type: string): GraphNode => ({
  id: alias(id),
  asset_id: id,
  asset_type,
  namespace: "default",
  label: humanNames[id] ?? id.split("/").at(-1) ?? id,
});
export const edge = (
  source: string,
  target: string,
  link_type: string,
  event_id = "catalog-import-1",
): GraphEdge => ({
  source: alias(source),
  target: alias(target),
  kind: "catalog",
  link_type,
  operator: "CATALOG_IMPORT",
  event_id,
});
const measures = metrics.flatMap((id, index) =>
  [fields[index === 0 ? 0 : index + 2], "date", "status"].map((field) =>
    edge(id, `${orders}/${field}`, "measures"),
  ),
);
const dimensions = ["retail_region", "retail_channel", "retail_segment"];
const sliced = metrics.flatMap((id) =>
  dimensions.map((dimension) => edge(id, dimension, "sliced_by")),
);
const derived = [
  edge(paidId, `${summary}/paid_amount`, "derived"),
  edge(paidId, `${summary}/paid_amount`, "derived", "another-backing-event"),
  edge(`${orders}/date`, `${summary}/date`, "derived"),
  edge("other/source/paid", `${summary}/paid_amount`, "derived"),
];
export const fixture: ObjectData = {
  ...objectData,
  target: { kind: "column", id: paidId },
  catalog: column,
  table: {
    ...detail,
    columns: fields.map((field) => ({
      ...column,
      name: field,
      asset_ref: { ...column.asset_ref, asset_id: `${orders}/${field}` },
    })),
  },
  metric: { ...metric, definition: { ...metric.definition, dimensions } },
  graph: {
    truncated: false,
    events: [],
    nodes: [
      node(orders, "table"),
      node(summary, "table"),
      ...fields.map((field) => node(`${orders}/${field}`, "column")),
      ...["paid_amount", "date"].map((field) =>
        node(`${summary}/${field}`, "column"),
      ),
      node("other/source/paid", "column"),
      ...metrics.map((id) => node(id, "metric")),
      ...dimensions.map((id) => node(id, "dimension")),
      node(term.asset_ref.asset_id, "term"),
      node("term/Other", "term"),
      node("term/Orphan", "term"),
    ],
    edges: [
      ...measures,
      ...sliced,
      ...derived,
      edge("retail_revenue", paidId, "measures", "duplicate-reference"),
      edge(term.asset_ref.asset_id, "retail_revenue", "means"),
      edge("term/Other", "order_count", "means"),
    ],
  },
};
export const reference = (id: string) => {
  const item = fixture.graph.nodes.find((entry) => entry.id === id);
  return {
    asset_id: item?.asset_id ?? id,
    asset_type: item?.asset_type ?? "column",
    namespace: "default",
  };
};
fixture.catalogNeighbors = {
  asset_id: orders,
  truncated: false,
  objects: fixture.graph.nodes.map((item) => ({
    asset_ref: { ...reference(item.id), display_name: item.asset_id },
    name: item.label,
    table_id:
      item.asset_type === "column"
        ? item.asset_id.split("/").slice(0, -1).join("/")
        : null,
    revision: 1,
    properties: {},
  })),
  links: fixture.graph.edges.map((item) => ({
    source: reference(item.source),
    target: reference(item.target),
    kind: item.link_type as components["schemas"]["CatalogLink"]["kind"],
    producer_event_id: item.event_id,
  })),
};
