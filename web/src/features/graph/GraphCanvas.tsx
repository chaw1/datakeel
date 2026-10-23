import { useId, useMemo } from "react";

import { useI18n } from "../../i18n/useI18n";
import { catalogLinkLabel } from "../lineage/catalogLabels";
import { layoutGraph } from "../lineage/layout";

import { ArchiveCard } from "./ArchiveCard";
import { graphKindLabel } from "./archiveModel";
import { useGraphScroll } from "./useGraphScroll";

import type { ArchiveProjection } from "./archiveModel";
import type { GraphNode } from "../../api/types";

export function GraphCanvas({
  projection,
  selected,
  center,
  onSelect,
  onNavigate,
}: {
  projection: ArchiveProjection;
  selected: string | null;
  center?: string;
  onSelect: (id: string) => void;
  onNavigate?: (node: GraphNode) => void;
}) {
  const { t } = useI18n();
  const markerId = useId();
  const { graph, groups } = projection;
  const layout = useMemo(
    () => layoutGraph(graph.nodes, graph.edges),
    [graph.nodes, graph.edges],
  );
  const { ref, overflow, scroll } = useGraphScroll(layout.width);
  return (
    <>
      {(overflow.left || overflow.right) && (
        <div className="graph-scroll-hint">
          <span>{t("graphScrollHint")}</span>
          <div>
            <button
              type="button"
              aria-label={t("graphScrollLeft")}
              disabled={!overflow.left}
              onClick={() => {
                scroll(-1);
              }}
            >
              ←
            </button>
            <button
              type="button"
              aria-label={t("graphScrollRight")}
              disabled={!overflow.right}
              onClick={() => {
                scroll(1);
              }}
            >
              →
            </button>
          </div>
        </div>
      )}
      <div
        ref={ref}
        className="graph-scroll"
        aria-label={t("scrollableLineageGraph")}
      >
        <div
          className="archive-stage"
          style={{ width: layout.width, height: layout.height }}
        >
          <svg
            className="graph"
            width={layout.width}
            height={layout.height}
            role="group"
            aria-label={t("dataLineageSelectAnAssetToInspectItsEvents")}
          >
            {layout.columns.map((column) => (
              <text
                key={column.kind}
                x={column.x}
                y={30}
                className="graph-column-title"
              >
                {graphKindLabel(column.kind, t)}
              </text>
            ))}
            <defs>
              <marker
                id={markerId}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M0 0 10 5 0 10Z" fill="var(--muted)" />
              </marker>
            </defs>
            {graph.edges.map((edge, index) => {
              const start = layout.positions.get(edge.source);
              const end = layout.positions.get(edge.target);
              if (!start || !end) return null;
              const x1 = start.x + 210;
              const y1 = start.y + 40;
              const semantic = edge.kind === "semantic";
              const x2 = semantic ? end.x + 210 : end.x;
              const y2 = end.y + 40;
              return (
                <g
                  key={`${edge.assertion?.id ?? edge.event_id ?? "edge"}-${String(index)}`}
                >
                  <path
                    className={`graph-edge ${edge.kind} ${selected && (edge.source === selected || edge.target === selected) ? "active" : ""}`}
                    d={`M${String(x1)} ${String(y1)} C${String(x1 + 24)} ${String(y1)},${String(semantic ? x2 + 30 : x2 - 24)} ${String(y2)},${String(x2)} ${String(y2)}`}
                    markerEnd={semantic ? undefined : `url(#${markerId})`}
                  />
                  <title>
                    {edge.kind === "catalog"
                      ? catalogLinkLabel(edge.link_type ?? edge.operator, t)
                      : edge.operator}
                  </title>
                </g>
              );
            })}
          </svg>
          {groups.map((group) => {
            const position = layout.positions.get(group.node.id);
            return (
              position && (
                <ArchiveCard
                  key={group.node.id}
                  group={group}
                  position={position}
                  selected={selected === group.node.id}
                  center={group.members.some(
                    (node) => node.id === center || node.asset_id === center,
                  )}
                  connections={
                    graph.edges.filter(
                      (edge) =>
                        edge.source === group.node.id ||
                        edge.target === group.node.id,
                    ).length
                  }
                  onSelect={() => {
                    onSelect(group.node.id);
                  }}
                  onNavigate={onNavigate}
                />
              )
            );
          })}
        </div>
      </div>
    </>
  );
}
