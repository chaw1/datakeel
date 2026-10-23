import { get, ApiError } from "./client";
import { queryEvidence } from "./evidence";

import type {
  CatalogObject,
  CatalogTableDetail,
  ImpactResult,
  MetricCard,
} from "./catalog";
import type { components } from "./generated";
import type {
  ActionPlan,
  ActionRun,
  Dataset,
  EvidenceSample,
  FileItem,
  Graph,
  Quality,
  Report,
  Version,
} from "./types";
import type { ObjectTarget } from "../features/object/navigation";

export type MetricHistory = components["schemas"]["MetricHistory"];
export type ObjectData = {
  target: ObjectTarget;
  name: string;
  graph: Graph;
  dataset?: Dataset;
  file?: FileItem;
  version?: Version;
  files: FileItem[];
  versions: Version[];
  quality: Quality | null;
  report: Report | null;
  samples: EvidenceSample[];
  table?: CatalogTableDetail;
  catalog?: CatalogObject;
  catalogNeighbors?: ImpactResult;
  metric?: MetricCard;
  metricHistory?: MetricHistory;
  action?: ActionRun;
  plan?: ActionPlan;
};
export function objectGraphPath(
  target: ObjectTarget,
  expanded = false,
): string {
  const query = new URLSearchParams({
    asset_id:
      target.kind === "version" ? (target.datasetId ?? target.id) : target.id,
    hops: "2",
    max_nodes: expanded ? "1000" : "25",
    include_catalog: "true",
    include_semantic: "true",
    collapse: String(!expanded),
  });
  return `/api/lineage/graph?${query.toString()}`;
}
async function optional<T>(path: string): Promise<T | null> {
  try {
    return await get<T>(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
async function context(target: ObjectTarget): Promise<ObjectTarget> {
  if (!["file", "version"].includes(target.kind) || target.datasetId)
    return target;
  const results = await get<components["schemas"]["SearchResult"][]>(
    `/api/search?${new URLSearchParams({ q: target.id, limit: "100" }).toString()}`,
  );
  const found = results.find(
    (item) => item.kind === target.kind && item.id === target.id,
  );
  if (!found?.dataset_id) throw new Error(`Object not found: ${target.id}`);
  return {
    ...target,
    datasetId: found.dataset_id,
    versionId: target.versionId ?? found.version_id ?? undefined,
  };
}
async function samples(
  datasetId: string,
  versionId?: string,
  includeDeleted = false,
): Promise<EvidenceSample[]> {
  const items: EvidenceSample[] = [];
  let cursor: string | null = null;
  do {
    const page = await queryEvidence({
      schema_version: "1.1",
      namespace: "default",
      object_type: "file",
      include_deleted: includeDeleted,
      limit: 10000,
      page_size: 200,
      sort: "review",
      dataset_id: datasetId,
      version_ids: versionId ? [versionId] : [],
      cursor,
    });
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return items;
}
async function datasetData(target: ObjectTarget): Promise<Partial<ObjectData>> {
  const datasetId = target.kind === "dataset" ? target.id : target.datasetId;
  if (!datasetId) throw new Error(`Dataset context missing: ${target.id}`);
  const base = `/api/datasets/${encodeURIComponent(datasetId)}`;
  const [dataset, files, versions, quality, report, evidence] =
    await Promise.all([
      get<Dataset>(base),
      get<FileItem[]>(`${base}/files`),
      get<Version[]>(`${base}/versions`),
      optional<Quality>(`${base}/quality`),
      optional<Report>(`${base}/report`),
      samples(
        datasetId,
        target.kind === "version" ? target.id : target.versionId,
        target.kind !== "dataset",
      ),
    ]);
  versions.sort((a, b) => b.created_at - a.created_at);
  const version = versions.find(
    (item) =>
      item.id === (target.kind === "version" ? target.id : target.versionId),
  );
  const file =
    target.kind === "file"
      ? (
          version?.manifest ?? [
            ...files,
            ...versions.flatMap((item) => item.manifest),
          ]
        ).find((item) => item.id === target.id)
      : undefined;
  if (target.kind === "file" && !file)
    throw new Error(`File not found: ${target.id}`);
  if (target.kind === "version" && !version)
    throw new Error(`Version not found: ${target.id}`);
  return {
    dataset,
    files,
    versions,
    quality,
    report,
    file,
    version,
    samples:
      target.kind === "file"
        ? evidence.filter((item) => item.asset_ref.asset_id === target.id)
        : evidence,
    name:
      file?.filename ??
      (version
        ? `${dataset.name} · ${String(versions.length - versions.indexOf(version))}`
        : dataset.name),
  };
}
async function catalogData(target: ObjectTarget): Promise<Partial<ObjectData>> {
  const encoded = encodeURIComponent(target.id);
  if (target.kind === "table") {
    const table = await get<CatalogTableDetail>(
      `/api/catalog/tables/${encoded}`,
    );
    return {
      table,
      catalog: table.table,
      catalogNeighbors: table.neighbors,
      name: table.table.name,
    };
  }
  if (target.kind === "metric") {
    const [metric, metricHistory, catalogNeighbors] = await Promise.all([
      get<MetricCard>(`/api/catalog/metrics/${encoded}`),
      get<MetricHistory>(`/api/catalog/metrics/${encoded}/history`),
      get<ImpactResult>(`/api/catalog/neighbors?asset_id=${encoded}`),
    ]);
    return {
      metric,
      metricHistory,
      catalogNeighbors,
      name: metric.definition.name,
    };
  }
  const [catalog, catalogNeighbors] = await Promise.all([
    get<CatalogObject>(`/api/catalog/objects/${encoded}`),
    get<ImpactResult>(`/api/catalog/neighbors?asset_id=${encoded}`),
  ]);
  return { catalog, catalogNeighbors, name: catalog.name };
}
async function actionData(target: ObjectTarget): Promise<Partial<ObjectData>> {
  const runs = await get<ActionRun[]>("/api/actions/runs");
  const action = runs.find((item) => item.id === target.id);
  if (!action) throw new Error(`Action run not found: ${target.id}`);
  const plan = await get<ActionPlan>(
    `/api/actions/plans/${encodeURIComponent(action.plan_id)}`,
  );
  return { action, plan, name: action.action_type };
}
export async function loadObject(initial: ObjectTarget): Promise<ObjectData> {
  const target = await context(initial);
  const [graph, details] = await Promise.all([
    get<Graph>(objectGraphPath(target)),
    ["dataset", "file", "version"].includes(target.kind)
      ? datasetData(target)
      : target.kind === "action_run"
        ? actionData(target)
        : catalogData(target),
  ]);
  if (
    details.action?.receipt &&
    !graph.events.some(
      (event) => event.event_id === details.action?.receipt?.event_id,
    )
  )
    graph.events.push(details.action.receipt);
  if (details.file) {
    const node = graph.nodes.find((item) => item.asset_id === details.file?.id);
    details.file = {
      ...details.file,
      metadata: {
        ...details.file.metadata,
        ...(node?.deleted != null ? { deleted: node.deleted } : {}),
        ...(node?.quarantined != null ? { quarantined: node.quarantined } : {}),
      },
    };
  }
  return {
    target,
    name: target.id,
    files: [],
    versions: [],
    quality: null,
    report: null,
    samples: [],
    graph,
    ...details,
  };
}
