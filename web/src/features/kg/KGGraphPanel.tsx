import { useId, useMemo, useState } from "react";

import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";

import { KGBadge } from "./KGBadge";
import { useKGQuery } from "./useKGQuery";

import type { KGQuery } from "../../api/kg";

export function KGGraphPanel({
  query,
  revision,
  onInspect,
}: {
  query: KGQuery;
  revision: number;
  onInspect: (id: string) => void;
}) {
  const { t } = useI18n();
  const marker = useId();
  const [retry, setRetry] = useState(0);
  const bounded = useMemo(() => ({ ...query, limit: 60 }), [query]);
  const resource = useKGQuery("/api/kg/graph", bounded, revision + retry);
  const nodes = resource.value?.nodes ?? [];
  const edges = resource.value?.edges ?? [];
  const types = [...new Set(nodes.map((node) => node.entity_type))].sort();
  const positions = new Map<string, { x: number; y: number }>();
  let count = 0;
  types.forEach((type, column) => {
    const group = nodes.filter((node) => node.entity_type === type);
    count = Math.max(count, group.length);
    group.forEach((node, row) =>
      positions.set(node.id, { x: 36 + column * 250, y: 60 + row * 105 }),
    );
  });
  const width = Math.max(700, types.length * 250 + 72);
  const height = Math.max(240, count * 105 + 90);
  return (
    <section className="kg-graph-panel">
      <p className="muted">{t("kgGraphNote")}</p>
      <p className="muted">{t("kgGraphLimit")}</p>
      <div className="kg-graph-legend">
        {(["accepted", "candidate", "needs_review", "rejected"] as const).map(
          (status) => (
            <span className={`kg-legend ${status}`} key={status}>
              <i />
              <KGBadge value={status} />
            </span>
          ),
        )}
      </div>
      <ResourceState
        {...resource}
        onRetry={() => {
          setRetry((value) => value + 1);
        }}
      />
      {resource.value?.truncated && (
        <p className="warning-banner">{t("kgBounded")}</p>
      )}
      <div className="kg-graph-scroll">
        <svg
          width={width}
          height={height}
          role="group"
          aria-label={t("kgGraphLabel")}
        >
          <defs>
            <marker
              id={marker}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M0 0 10 5 0 10Z" fill="var(--muted)" />
            </marker>
          </defs>
          {types.map((type, index) => (
            <text
              className="kg-graph-type"
              key={type}
              x={36 + index * 250}
              y={30}
            >
              {type}
            </text>
          ))}
          {edges.map((edge) => {
            const from = positions.get(edge.source);
            const to = positions.get(edge.target);
            if (!from || !to) return null;
            const forward = from.x < to.x;
            const x1 = from.x + (forward ? 190 : 0);
            const x2 = to.x + (forward ? 0 : 190);
            const y1 = from.y + 30;
            const y2 = to.y + 30;
            const style =
              edge.status === "rejected"
                ? "rejected"
                : edge.verification === "needs_review"
                  ? "needs_review"
                  : edge.status;
            return (
              <a
                key={edge.id}
                href="#/kg"
                aria-label={`${t("kgInspect")}: ${edge.predicate}`}
                onClick={(event) => {
                  event.preventDefault();
                  onInspect(edge.id);
                }}
              >
                <path
                  className={`kg-edge ${style}`}
                  d={`M${String(x1)} ${String(y1)} C${String(x1 + (forward ? 35 : -35))} ${String(y1)},${String(x2 + (forward ? -35 : 35))} ${String(y2)},${String(x2)} ${String(y2)}`}
                  markerEnd={`url(#${marker})`}
                />
                <title>
                  {edge.predicate} · {edge.status} · {edge.verification ?? ""}
                </title>
              </a>
            );
          })}
          {nodes.map((node) => {
            const position = positions.get(node.id);
            if (!position) return null;
            return (
              <g
                key={node.id}
                transform={`translate(${String(position.x)} ${String(position.y)})`}
              >
                <title>
                  {node.label} ·{" "}
                  {t("kgMembers", { count: node.members.length })}
                </title>
                <rect className="kg-graph-node" width="190" height="62" />
                <text x="12" y="25" className="kg-graph-name">
                  {node.label.length > 22
                    ? `${node.label.slice(0, 21)}…`
                    : node.label}
                </text>
                <text x="12" y="47" className="kg-graph-meta">
                  {node.members.length > 1
                    ? t("kgMembers", { count: node.members.length })
                    : node.entity_type}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      {!nodes.length && !resource.loading && !resource.error && (
        <p>{t("kgEmpty")}</p>
      )}
    </section>
  );
}
