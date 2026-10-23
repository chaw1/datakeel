import { translator } from "../../i18n/context";
import {
  localizedCatalogName,
  localizedObjectName,
} from "../../i18n/graphCatalogNames";
import { catalogKindLabel } from "../lineage/catalogLabels";

import type { Graph, GraphEdge, GraphNode } from "../../api/types";
import type { Locale, Translate } from "../../i18n/context";

export type ArchiveGroup = { node: GraphNode; members: GraphNode[] };
export type ArchiveProjection = { graph: Graph; groups: ArchiveGroup[] };
export const edgeKinds = ["lineage", "semantic", "catalog"] as const;
export type EdgeKind = (typeof edgeKinds)[number];
const uuid = /[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}/gi;

export function safeNodeName(node: GraphNode, locale: Locale = "en"): string {
  const t = translator(locale);
  const kind = node.asset_type;
  const raw = node.display_name?.trim() || node.label.trim();
  const name = kind === "term" ? raw.replace(/^term[/\\]/, "") : raw;
  const fallback = `${graphKindLabel(kind, t)} ${node.asset_id.slice(0, 8)}`;
  const genericNames = new Set([
    kind.replaceAll("_", " ").toLowerCase(),
    graphKindLabel(kind, translator("en")).toLowerCase(),
    graphKindLabel(kind, translator("zh")).toLowerCase(),
  ]);
  const hash = /^(?:(?:sha1|sha256|sha512):)?[\da-f]{32,}$/i.test(name);
  if (
    hash ||
    !name ||
    name === node.asset_id ||
    genericNames.has(name.toLowerCase())
  )
    return fallback;
  const readable = name.replace(uuid, "").replace(/^[\s/:.-]+|[\s/:.-]+$/g, "");
  if (!readable || genericNames.has(readable.toLowerCase())) return fallback;
  if (kind === "task" && readable === "Pipeline run")
    return t("graphPipelineRun");
  if (["version", "dataset_version"].includes(kind)) {
    const version = /^(\d+)\s*·\s*(.+)$/.exec(readable);
    if (version)
      return `${t("graphVersionName", { number: version[1] })} · ${version[2]}`;
  }
  if (["metric", "dimension"].includes(kind))
    return localizedCatalogName(readable, t);
  if (kind === "column") {
    const table = node.asset_id.split("/").at(-2);
    const qualified =
      !readable.includes(".") && table ? `${table}.${readable}` : readable;
    return localizedObjectName(kind, qualified, locale);
  }
  return localizedObjectName(kind, readable, locale);
}

export function middleEllipsis(value: string, length: number): string {
  const letters = Array.from(value);
  if (letters.length <= length) return value;
  const leading = Math.max(1, Math.floor((length - 1) / 3));
  return `${letters.slice(0, leading).join("")}…${letters.slice(-(length - leading - 1)).join("")}`;
}

export function archiveName(node: GraphNode, locale: Locale = "en") {
  const readable = safeNodeName(node, locale);
  const separator =
    node.asset_type === "file"
      ? /[\\/]/
      : node.asset_type === "column"
        ? /\./
        : null;
  const parts = separator
    ? readable.split(separator).filter(Boolean)
    : [readable];
  const prefix =
    parts.length > 1
      ? `${parts.at(-2) ?? ""}${node.asset_type === "file" ? "/" : "."}`
      : "";
  const name = parts.at(-1) ?? readable;
  const hasCjk = (value: string) => /[\u3400-\u9fff]/.test(value);
  return {
    prefix: middleEllipsis(prefix, hasCjk(prefix) ? 14 : 20),
    name: ["version", "dataset_version"].includes(node.asset_type)
      ? name
      : middleEllipsis(name, hasCjk(name) ? 18 : 30),
  };
}

export function graphKindLabel(kind: string, t: Translate): string {
  const key = {
    dataset: "graphDataset",
    file: "graphFile",
    dataset_version: "graphVersion",
    version: "graphVersion",
    action_run: "graphActionRun",
    artifact: "graphArtifact",
    aggregate: "graphAggregate",
    task: "graphTask",
    knowledge_bundle: "graphKnowledgeBundle",
    question: "graphQuestion",
  } as const;
  return kind in key
    ? t(key[kind as keyof typeof key])
    : catalogKindLabel(kind, t).replaceAll("_", " ");
}

export function edgeKindLabel(kind: EdgeKind, t: Translate): string {
  return t(
    {
      lineage: "lineageEdges",
      semantic: "semanticEdges",
      catalog: "catalogEdges",
    }[kind] as "lineageEdges" | "semanticEdges" | "catalogEdges",
  );
}

export function aggregateInfo(
  node: GraphNode,
): { kind: EdgeKind; count: number } | null {
  const match = /^aggregate:(lineage|semantic|catalog):(\d+)$/.exec(
    node.asset_id,
  );
  return node.asset_type === "aggregate" && match
    ? { kind: match[1] as EdgeKind, count: Number(match[2]) }
    : null;
}

function groupKey(node: GraphNode): string {
  return node.asset_type === "action_run" && node.display_name
    ? `action_run:${node.display_name}`
    : `asset:${node.id}`;
}

function mergedGroups(nodes: GraphNode[], focusId?: string): ArchiveGroup[] {
  const grouped = new Map<string, GraphNode[]>();
  for (const node of nodes) {
    const key = groupKey(node);
    grouped.set(key, [...(grouped.get(key) ?? []), node]);
  }
  return [...grouped.values()].map((members) => ({
    node:
      members.find(
        (node) => node.id === focusId || node.asset_id === focusId,
      ) ?? members[0],
    members,
  }));
}

function remappedEdges(
  edges: GraphEdge[],
  groups: ArchiveGroup[],
): GraphEdge[] {
  const ids = new Map(
    groups.flatMap((group) =>
      group.members.map((member) => [member.id, group.node.id] as const),
    ),
  );
  return edges.flatMap((edge) => {
    const source = ids.get(edge.source);
    const target = ids.get(edge.target);
    return source && target && source !== target
      ? [{ ...edge, source, target }]
      : [];
  });
}

function orderedGroups(graph: Graph, focusId?: string) {
  const groups = mergedGroups(graph.nodes, focusId);
  const byKey = new Map(groups.map((group) => [groupKey(group.node), group]));
  const byId = new Map(
    groups.flatMap((group) =>
      group.members.map((node) => [node.id, groupKey(group.node)] as const),
    ),
  );
  const adjacency = new Map<string, { target: string; kind: EdgeKind }[]>(
    [...byKey.keys()].map((key) => [key, []]),
  );
  for (const edge of graph.edges) {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (source && target) {
      adjacency.get(source)?.push({ target, kind: edge.kind });
      adjacency.get(target)?.push({ target: source, kind: edge.kind });
    }
  }
  const focused = groups.find((group) =>
    group.members.some(
      (node) => node.id === focusId || node.asset_id === focusId,
    ),
  );
  const root = focused ? groupKey(focused.node) : null;
  const roots = [
    ...(root ? [root] : []),
    ...[...byKey.keys()].filter((key) => key !== root).sort(),
  ];
  const kinds = new Map<string, EdgeKind>();
  const ordered: ArchiveGroup[] = [];
  for (const key of roots) {
    if (kinds.has(key)) continue;
    kinds.set(key, "lineage");
    const pending = [key];
    for (let index = 0; index < pending.length; index++) {
      const current = pending[index];
      const group = byKey.get(current);
      if (group) ordered.push(group);
      const neighbors = [...(adjacency.get(current) ?? [])].sort(
        (a, b) =>
          edgeKinds.indexOf(a.kind) - edgeKinds.indexOf(b.kind) ||
          (a.target < b.target ? -1 : a.target > b.target ? 1 : 0),
      );
      for (const neighbor of neighbors) {
        if (!kinds.has(neighbor.target)) {
          kinds.set(neighbor.target, neighbor.kind);
          pending.push(neighbor.target);
        }
      }
    }
  }
  return {
    groups: ordered,
    kind: (group: ArchiveGroup) => kinds.get(groupKey(group.node)) ?? "lineage",
  };
}

export function archiveProjection(
  graph: Graph,
  focusId?: string,
): ArchiveProjection {
  const ordered = orderedGroups(graph, focusId);
  let groups = ordered.groups;
  let truncated = graph.truncated;
  if (groups.length > 25) {
    let keep = 25;
    while (keep + new Set(groups.slice(keep).map(ordered.kind)).size > 25)
      keep--;
    const visible = groups.slice(0, keep);
    for (const kind of edgeKinds) {
      const hidden = groups
        .slice(keep)
        .filter((group) => ordered.kind(group) === kind);
      if (!hidden.length) continue;
      const id = `aggregate:${kind}:${String(hidden.length)}`;
      const node: GraphNode = {
        id,
        asset_id: id,
        asset_type: "aggregate",
        namespace: "graph",
        label: id,
      };
      visible.push({ node, members: hidden.flatMap((entry) => entry.members) });
    }
    groups = visible;
    truncated = true;
  }
  return {
    groups,
    graph: {
      ...graph,
      nodes: groups.map((group) => group.node),
      edges: remappedEdges(graph.edges, groups),
      truncated,
    },
  };
}

export function expansionNodes(
  graph: Graph,
  visible: Graph,
  kind: EdgeKind,
  focusId?: string,
): GraphNode[] {
  const existing = new Set(visible.nodes.map((node) => node.id));
  const ordered = orderedGroups(graph, focusId);
  return ordered.groups
    .filter(
      (group) =>
        group.node.asset_type !== "aggregate" &&
        !group.members.some((node) => existing.has(node.id)) &&
        ordered.kind(group) === kind,
    )
    .flatMap((group) => group.members);
}
