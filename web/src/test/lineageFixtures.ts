import { graph } from "./fixtures";

import type { Graph, GraphEdge } from "../api/types";

const subject = {
  asset_id: "output",
  asset_type: "file",
  namespace: "default",
  version: "source-version",
};
const object = { ...subject, asset_id: "source" };
export const semanticEdge: GraphEdge = {
  source: "output",
  target: "source",
  kind: "semantic",
  operator: "similar_to",
  link_type: "similar_to",
  assertion: {
    id: "pair-1",
    subject,
    object,
    predicate: "near_duplicate_of",
    status: "candidate",
    schema_version: "1.0",
    producer_event_id: "extract-1",
    run_id: "extract-run",
    distance: 2,
    extractor: { id: "evidence.near_duplicate", version: "1" },
    anchors: [
      {
        asset_ref: subject,
        content_revision: "a".repeat(64),
        schema_version: "1.0",
        selector: { type: "whole" },
      },
    ],
  },
};
export const semanticGraph: Graph = {
  ...graph,
  edges: [...graph.edges, semanticEdge],
  truncated: true,
};
