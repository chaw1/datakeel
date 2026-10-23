import { useMemo, useState } from "react";

import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";
import { LineageDetails } from "../lineage/LineageDetails";

import {
  aggregateInfo,
  archiveProjection,
  edgeKindLabel,
  expansionNodes,
  safeNodeName,
} from "./archiveModel";
import { GraphCanvas } from "./GraphCanvas";
import { GraphExpansion } from "./GraphExpansion";
import { RelationList } from "./RelationList";

import type { Graph, GraphNode, LineageEvent } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

import "./graph.css";

type Expansion = {
  title: string;
  nodes: GraphNode[];
  truncated: boolean;
  graph: Graph;
};

export function RelationGraph({
  graph,
  compact = false,
  focus,
  onNavigate,
  loadExpansion,
}: {
  graph: Graph;
  compact?: boolean;
  focus?: LineageTarget;
  onNavigate?: (node: GraphNode) => void;
  loadExpansion?: () => Promise<Graph>;
}) {
  const { t, locale } = useI18n();
  const projection = useMemo(
    () => archiveProjection(graph, focus?.assetId),
    [graph, focus?.assetId],
  );
  const [chosen, setChosen] = useState<string | null>(null);
  const [expansion, setExpansion] = useState<Expansion | null>(null);
  const [expandedNode, setExpandedNode] = useState<GraphNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const selected =
    chosen ??
    projection.groups.find((group) =>
      group.members.some(
        (node) =>
          node.id === focus?.assetId || node.asset_id === focus?.assetId,
      ),
    )?.node.id ??
    projection.graph.edges.find((edge) => edge.event_id === focus?.eventId)
      ?.target ??
    null;
  const group = projection.groups.find((item) => item.node.id === selected);
  const selectedNode = expandedNode ?? group?.node;
  const selectedIds = new Set(
    expandedNode ? [expandedNode.id] : group?.members.map((node) => node.id),
  );
  const source = expandedNode && expansion ? expansion.graph : graph;
  const connectedEdges = source.edges.filter(
    (edge) => selectedIds.has(edge.source) || selectedIds.has(edge.target),
  );
  const events: LineageEvent[] = [];
  const seen = new Set<string>();
  for (const edge of connectedEdges) {
    const event =
      edge.event ??
      source.events.find((item) => item.event_id === edge.event_id);
    if (event && edge.kind !== "semantic" && !seen.has(event.event_id ?? "")) {
      seen.add(event.event_id ?? "");
      events.push(event);
    }
  }
  const focusedEvent =
    chosen === null && focus?.eventId
      ? graph.events.find((event) => event.event_id === focus.eventId)
      : undefined;
  if (focusedEvent && !seen.has(focusedEvent.event_id ?? ""))
    events.push(focusedEvent);

  async function select(id: string) {
    setChosen(id);
    setExpandedNode(null);
    setExpansion(null);
    setError(false);
    const selectedGroup = projection.groups.find((item) => item.node.id === id);
    if (!selectedGroup) return;
    const aggregate = aggregateInfo(selectedGroup.node);
    if (aggregate) {
      setLoading(true);
      try {
        const expanded = loadExpansion ? await loadExpansion() : graph;
        const members = selectedGroup.members.filter(
          (node) => node.asset_type !== "aggregate",
        );
        const nodes = members.length
          ? members
          : expansionNodes(
              expanded,
              {
                ...projection.graph,
                nodes: projection.groups.flatMap((item) => item.members),
              },
              aggregate.kind,
              focus?.assetId,
            );
        setExpansion({
          title: t("graphExpandRelations", {
            kind: edgeKindLabel(aggregate.kind, t),
          }),
          nodes,
          truncated: expanded.truncated && members.length === 0,
          graph: expanded,
        });
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    } else if (selectedGroup.members.length > 1) {
      setExpansion({
        title: t("graphGroupMembers", {
          name: safeNodeName(selectedGroup.node, locale),
          count: selectedGroup.members.length,
        }),
        nodes: selectedGroup.members,
        truncated: false,
        graph,
      });
    }
  }

  if (!graph.nodes.length)
    return (
      <div className="empty-state">
        <Icon name="lineage" size={28} />
        <h3>{t("theStoryStartsHere")}</h3>
        <p>{t("lineageAppearsAsTheWorkerRunsTransformations")}</p>
      </div>
    );
  return (
    <div className={compact ? "lineage compact" : "lineage"}>
      <div className="graph-toolbar">
        <div className="graph-legend" role="group" aria-label={t("edgeKinds")}>
          <span className="legend-dot" />
          <span>{t("asset")}</span>
          <span className="legend-line" />
          <span>{t("lineageEdges")}</span>
          <span className="legend-line semantic" />
          <span>{t("semanticEdges")}</span>
          <span className="legend-line catalog" />
          <span>{t("catalogEdges")}</span>
        </div>
        <span className="graph-counts">
          {t("graphAssetCount", { count: projection.groups.length })} ·{" "}
          {t("graphEdgeCount", { count: projection.graph.edges.length })}
        </span>
      </div>
      {projection.graph.truncated && (
        <p className="graph-hint" role="status">
          {t("graphTruncated")}
        </p>
      )}
      <GraphCanvas
        projection={projection}
        selected={selected}
        center={focus?.assetId}
        onSelect={(id) => {
          void select(id);
        }}
        onNavigate={onNavigate}
      />
      {loading && <p role="status">{t("loadingData")}</p>}
      {error && <p role="alert">{t("graphLoadError")}</p>}
      {expansion && (
        <GraphExpansion
          key={expansion.title}
          {...expansion}
          onNavigate={onNavigate}
          onSelect={(node) => {
            setExpandedNode(node);
            setChosen(node.id);
          }}
        />
      )}
      <RelationList
        graph={projection.graph}
        onSelect={(id) => {
          void select(id);
        }}
      />
      {selectedNode && selectedNode.asset_type !== "aggregate" && (
        <LineageDetails
          node={selectedNode}
          nodes={source.nodes}
          edges={connectedEdges}
          events={events}
          onClose={() => {
            setChosen("");
            setExpandedNode(null);
          }}
        />
      )}
    </div>
  );
}
