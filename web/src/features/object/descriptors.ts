import { bytes, date, display } from "../../lib/format";

import { objectHref } from "./navigation";

import type { ObjectKind, ObjectTarget } from "./navigation";
import type { CatalogObject } from "../../api/catalog";
import type { ObjectData } from "../../api/objects";
import type { Graph, GraphEdge, LineageEvent } from "../../api/types";
import type { MessageKey } from "../../i18n/en";

export const kindLabels: Record<ObjectKind, MessageKey> = {
  dataset: "objDataset",
  file: "objFile",
  version: "objVersion",
  action_run: "objAction",
  table: "objTable",
  column: "objColumn",
  metric: "objMetric",
  term: "objTerm",
};
export type ObjectFact = {
  label: MessageKey;
  value: string | number;
  href: string;
};
export function eventsFor(data: ObjectData): LineageEvent[] {
  return data.graph.events
    .filter(
      (event) =>
        data.target.kind !== "version" ||
        (event.outputs ?? []).some((ref) => ref.version === data.version?.id),
    )
    .sort((a, b) => (b.occurred_at ?? "").localeCompare(a.occurred_at ?? ""));
}
export function objectStatus(data: ObjectData): MessageKey {
  if (data.dataset && data.target.kind === "dataset")
    return data.versions.length ? "objWithVersion" : "objNoVersion";
  if (data.file)
    return data.file.metadata?.deleted
      ? "deletedFile"
      : data.file.metadata?.quarantined
        ? "quarantined"
        : "objNormal";
  if (data.version)
    return data.versions[0]?.id === data.version.id
      ? "objCurrent"
      : "objHistorical";
  if (data.action) return data.action.status;
  if (data.metric)
    return data.metric.status === "resolved" ? "catResolved" : "catUnresolved";
  if (data.target.kind === "term")
    return objectRelationEdges(data, data.target, "means").length > 0
      ? "objLinked"
      : "objOrphan";
  return data.catalog ? "objImported" : "objUnresolved";
}
export function objectCatalogGraph(data: ObjectData): Graph | undefined {
  const neighbors = data.catalogNeighbors ?? data.table?.neighbors;
  if (!neighbors) return undefined;
  const names = new Map(
    neighbors.objects.map((item) => [item.asset_ref.asset_id, item.name]),
  );
  return {
    nodes: neighbors.objects.map((item) => {
      const name = catalogNodeName(item, names);
      return {
        ...item.asset_ref,
        id: item.asset_ref.asset_id,
        label: name,
        display_name: name,
      };
    }),
    edges: neighbors.links.map((link) => ({
      source: link.source.asset_id,
      target: link.target.asset_id,
      kind: "catalog",
      link_type: link.kind,
      operator: link.kind,
      event_id: link.producer_event_id,
    })),
    events: data.graph.events,
    truncated: neighbors.truncated,
  };
}

function catalogNodeName(
  item: CatalogObject,
  names: Map<string, string>,
): string {
  if (item.asset_ref.asset_type !== "column" || !item.table_id)
    return item.name;
  const tableName = names.get(item.table_id) ?? item.table_id.split("/").at(-1);
  return `${tableName ?? ""}.${item.name}`;
}

export function objectRelationEdges(
  data: ObjectData,
  target: ObjectTarget,
  relation: string,
): GraphEdge[] {
  const graph = objectCatalogGraph(data) ?? data.graph;
  const asset =
    target.kind === "version" ? (target.datasetId ?? target.id) : target.id;
  const sources = new Set(
    target.kind === "table" && relation === "derived"
      ? (data.table?.columns.map((column) => column.asset_ref.asset_id) ?? [])
      : [asset],
  );
  const ids = new Set([
    ...sources,
    ...graph.nodes
      .filter((node) => sources.has(node.asset_id))
      .map((node) => node.id),
  ]);
  return graph.edges.filter((edge) => {
    const matches =
      edge.kind === relation ||
      edge.link_type === relation ||
      (relation === "near_duplicate" &&
        edge.assertion?.predicate === "near_duplicate_of");
    if (!matches) return false;
    if (target.kind === "column" && relation === "measures")
      return ids.has(edge.target);
    const outgoing =
      (relation === "derived" && ["table", "column"].includes(target.kind)) ||
      (target.kind === "metric" &&
        ["measures", "sliced_by"].includes(relation)) ||
      (target.kind === "term" && relation === "means");
    return outgoing
      ? ids.has(edge.source)
      : ids.has(edge.source) || ids.has(edge.target);
  });
}

export function objectFacts(
  data: ObjectData,
  target: ObjectTarget,
): ObjectFact[] {
  const link = (
    label: MessageKey,
    value: string | number,
    extra: Partial<ObjectTarget> = {},
  ): ObjectFact => ({
    label,
    value,
    href: objectHref({ ...target, ...extra }),
  });
  const events = eventsFor(data);
  const latest = events.at(0);
  const history = (event?: LineageEvent): Partial<ObjectTarget> => ({
    tab: "history",
    eventId: event?.event_id,
  });
  const relation = (kind: string): Partial<ObjectTarget> => ({
    tab: "relations",
    relation: kind,
    section: kind,
  });
  const count = (kind: string) => {
    const ids = objectRelationEdges(data, target, kind).map((edge) =>
      target.kind === "column" && kind === "measures"
        ? edge.source
        : edge.target,
    );
    return new Set(
      ids.map(
        (id) => data.graph.nodes.find((node) => node.id === id)?.asset_id ?? id,
      ),
    ).size;
  };
  const descriptors: Record<ObjectKind, () => ObjectFact[]> = {
    dataset: () => [
      link(
        "objCurrentVersion",
        data.versions.length,
        data.versions[0]
          ? {
              kind: "version",
              id: data.versions[0].id,
              datasetId: target.id,
              tab: "facts",
            }
          : { tab: "versions" },
      ),
      link("objFileCount", data.dataset?.file_count ?? 0, { tab: "files" }),
      link("objQuality", data.quality?.total.toFixed(1) ?? "—", {
        tab: "quality",
      }),
      link(
        "objCandidates",
        data.samples.reduce(
          (n, sample) =>
            n +
            sample.assertions.filter((item) => item.status === "candidate")
              .length,
          0,
        ),
        { tab: "evidence" },
      ),
      link(
        "objUpdated",
        date(latest?.occurred_at ?? data.dataset?.created_at),
        history(latest),
      ),
    ],
    table: () => [
      link("objColumns", data.table?.columns.length ?? 0, {
        tab: "evidence",
        section: "fields",
      }),
      link("objSource", data.table?.table.source_id ?? "—", relation("source")),
      link("objDerived", count("derived"), relation("derived")),
      {
        label: "objMetrics",
        value: data.table?.metrics.length ?? 0,
        href: `#/catalog?${new URLSearchParams({ kind: "metric", table: target.id }).toString()}`,
      },
      link(
        "objImportedAt",
        date(
          events.find((event) => event.operator === "CATALOG_IMPORT")
            ?.occurred_at,
        ),
        history(
          events.find((event) => event.operator === "CATALOG_IMPORT") ??
            events.find(
              (event) => event.event_id === data.catalog?.producer_event_id,
            ),
        ),
      ),
    ],
    metric: () => [
      link("objRevision", data.metric?.definition.version ?? 0, {
        tab: "history",
      }),
      link(
        "objDimensions",
        data.metric?.definition.dimensions?.length ?? 0,
        relation("sliced_by"),
      ),
      link(
        "objMeasures",
        new Set(
          [
            data.metric?.definition.measure.column,
            data.metric?.definition.time.column,
            ...(data.metric?.definition.filters ?? []).map(
              (item) => item.column,
            ),
          ].filter(Boolean),
        ).size,
        relation("measures"),
      ),
      link("objOwner", data.metric?.definition.owner ?? "—", relation("owner")),
      link(
        "objModified",
        date(
          data.metricHistory?.audit.at(-1)?.created_at ?? latest?.occurred_at,
        ),
        {
          tab: "history",
          eventId:
            data.metricHistory?.audit.at(-1)?.event_id ?? latest?.event_id,
        },
      ),
    ],
    action_run: () => [
      link(
        "objReceipt",
        data.action?.status ?? "—",
        history(data.action?.receipt ?? undefined),
      ),
      link("objAffected", data.plan?.impact.object_count ?? 0, {
        tab: "evidence",
        section: "affected",
      }),
      link(
        "objExecuted",
        date(data.action?.completed_at ?? data.action?.created_at),
        history(data.action?.receipt ?? undefined),
      ),
      link(
        "objReceiptEvents",
        data.action?.receipt ? 1 : 0,
        relation("lineage"),
      ),
    ],
    file: () => [
      link("objSize", bytes(data.file?.size), {
        tab: "facts",
        section: "source-record",
      }),
      link("objQuality", data.samples.at(0)?.quality_score.toFixed(1) ?? "—", {
        tab: "quality",
      }),
      link(
        "objAssertions",
        data.samples.reduce((n, sample) => n + sample.assertions.length, 0),
        { tab: "evidence" },
      ),
      link("objDatasetSource", data.dataset?.name ?? "—", {
        kind: "dataset",
        id: data.dataset?.id ?? "",
        tab: "facts",
      }),
      link(
        "objNearDuplicates",
        data.samples.reduce(
          (n, sample) => n + sample.near_duplicates.length,
          0,
        ),
        relation("near_duplicate"),
      ),
    ],
    version: () => [
      link("objFileCount", data.version?.file_count ?? 0, { tab: "files" }),
      link("objCreated", date(data.version?.created_at), history(latest)),
      link(
        "objSize",
        bytes(data.version?.manifest.reduce((n, file) => n + file.size, 0)),
        { tab: "files" },
      ),
      link(
        "objProducer",
        latest?.operator ?? "—",
        producerTarget(data, target),
      ),
    ],
    column: () => [
      link("objDataType", display(data.catalog?.properties?.data_type), {
        tab: "facts",
      }),
      link("objNullable", display(data.catalog?.properties?.nullable), {
        tab: "facts",
      }),
      link("objDerived", count("derived"), relation("derived")),
      {
        label: "objMetrics",
        value: count("measures"),
        href: `#/catalog?${new URLSearchParams({ kind: "metric", column: target.id }).toString()}`,
      },
      link("objTableSource", data.catalog?.table_id?.split("/").at(-1) ?? "—", {
        kind: "table",
        id: data.catalog?.table_id ?? "",
        tab: "facts",
      }),
    ],
    term: () => [
      link("objLinkedObjects", count("means"), relation("means")),
      link("objImportedAt", date(latest?.occurred_at), history(latest)),
    ],
  };
  return descriptors[target.kind]();
}
function producerTarget(
  data: ObjectData,
  target: ObjectTarget,
): Partial<ObjectTarget> {
  const produced = eventsFor(data).find((event) =>
    (event.outputs ?? []).some((ref) => ref.version === data.version?.id),
  );
  const producer = [
    ...(produced?.outputs ?? []),
    ...(produced?.inputs ?? []),
  ].find((ref) => ref.asset_type === "action_run");
  return producer
    ? { kind: "action_run", id: producer.asset_id, tab: "history" }
    : {
        tab: "history",
        eventId: eventsFor(data).at(0)?.event_id,
        id: target.id,
      };
}
