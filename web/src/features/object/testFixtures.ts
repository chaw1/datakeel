import { vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";
import {
  dataset,
  file,
  graph,
  quality,
  report,
  version,
} from "../../test/fixtures";
import {
  column,
  detail,
  metric,
  metricObject,
  impact,
  source,
  table,
  term,
} from "../catalog/fixtures";

import type { ObjectData } from "../../api/objects";
import type { EvidenceSample, Graph } from "../../api/types";

export const sample: EvidenceSample = {
  asset_ref: { namespace: "default", asset_type: "file", asset_id: file.id },
  annotation_boxes: [],
  assertions: [],
  caption: "A sample.",
  caption_spans: [],
  dataset_id: dataset.id,
  deleted: false,
  filename: file.filename,
  near_duplicates: [],
  quality_score: 83.5,
  quarantined: false,
  source_version: version.id,
  split: "val",
  thumbnail_url: null,
};
export const objectGraph: Graph = {
  ...graph,
  nodes: [
    ...graph.nodes,
    {
      id: table.asset_ref.asset_id,
      asset_id: table.asset_ref.asset_id,
      asset_type: "table",
      namespace: "default",
      label: table.name,
      display_name: table.name,
    },
    {
      id: column.asset_ref.asset_id,
      asset_id: column.asset_ref.asset_id,
      asset_type: "column",
      namespace: "default",
      label: column.name,
      display_name: column.name,
    },
  ],
  events: [
    ...graph.events,
    {
      ...graph.events[0],
      event_id: "catalog-import-1",
      operator: "CATALOG_IMPORT",
    },
  ],
};
export const objectData: ObjectData = {
  target: { kind: "dataset", id: dataset.id },
  name: dataset.name,
  dataset,
  files: [file],
  versions: [version],
  quality,
  report,
  samples: [sample],
  graph: objectGraph,
};
export function mockObjects() {
  const fetch = vi.fn<(input: string, init?: RequestInit) => Promise<Response>>(
    (input) => {
      const url = new URL(input, "http://localhost");
      const path = decodeURIComponent(url.pathname);
      let payload: unknown = null;
      if (path === "/api/datasets") payload = [dataset];
      if (path === `/api/datasets/${dataset.id}`) payload = dataset;
      if (path.endsWith("/files")) payload = [file];
      if (path.endsWith("/versions")) payload = [version];
      if (path.endsWith("/quality")) payload = quality;
      if (path.endsWith("/report")) payload = report;
      if (path === "/api/lineage/graph") payload = objectGraph;
      if (path === "/api/evidence/query")
        payload = {
          items: [sample],
          next_cursor: null,
          total: 1,
          truncated: false,
        };
      if (path === "/api/actions/runs") payload = [actionRun];
      if (path.startsWith("/api/actions/plans/")) payload = actionPlan;
      if (path.startsWith("/api/catalog/tables/")) payload = detail;
      if (path.startsWith("/api/catalog/metrics/"))
        payload = path.endsWith("/history")
          ? { metric_id: metric.definition.id, versions: [metric], audit: [] }
          : metric;
      if (path.startsWith("/api/catalog/objects/"))
        payload = [column, term, source].find((item) =>
          path.endsWith(item.asset_ref.asset_id),
        );
      if (path === "/api/search")
        payload = [
          {
            kind: "file",
            id: file.id,
            name: file.filename,
            dataset_id: dataset.id,
            version_id: version.id,
          },
          {
            kind: "version",
            id: version.id,
            name: version.id,
            dataset_id: dataset.id,
            version_id: version.id,
          },
        ];
      if (path === "/api/catalog/neighbors") payload = { ...impact, links: [] };
      if (path === "/api/catalog/impact")
        payload = {
          asset_id: column.asset_ref.asset_id,
          objects: [column, table, metricObject],
          links: [],
          truncated: false,
        };
      return Promise.resolve(new Response(JSON.stringify(payload)));
    },
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
