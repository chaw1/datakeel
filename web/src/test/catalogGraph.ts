import { graph } from "./fixtures";

import type { Graph } from "../api/types";

export const catalogGraph: Graph = {
  nodes: [
    {
      ...graph.nodes[0],
      id: "metric",
      asset_id: "retail_revenue",
      asset_type: "metric",
      label: "Retail revenue",
    },
    {
      ...graph.nodes[0],
      id: "column-b",
      asset_id: "shop/main/orders/paid",
      asset_type: "column",
      label: "paid",
    },
    {
      ...graph.nodes[0],
      id: "table",
      asset_id: "shop/main/orders",
      asset_type: "table",
      label: "orders",
    },
    {
      ...graph.nodes[0],
      id: "column-a",
      asset_id: "shop/main/orders/date",
      asset_type: "column",
      label: "date",
    },
  ],
  edges: [
    {
      ...graph.edges[0],
      source: "metric",
      target: "column-b",
      kind: "catalog",
      link_type: "measures",
      operator: "measures",
    },
    {
      ...graph.edges[0],
      source: "table",
      target: "column-b",
      kind: "catalog",
      link_type: "contains",
      operator: "contains",
    },
  ],
  events: graph.events,
  truncated: false,
};
