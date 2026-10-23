import { useI18n } from "../../i18n/useI18n";
import { catalogLinkLabel } from "../lineage/catalogLabels";

import {
  aggregateInfo,
  edgeKindLabel,
  edgeKinds,
  safeNodeName,
} from "./archiveModel";

import type { Graph } from "../../api/types";

export function RelationList({
  graph,
  onSelect,
}: {
  graph: Graph;
  onSelect: (id: string) => void;
}) {
  const { t, locale } = useI18n();
  const names = new Map(
    graph.nodes.map((node) => {
      const aggregate = aggregateInfo(node);
      return [
        node.id,
        aggregate
          ? t("graphMoreOfKind", {
              count: aggregate.count,
              kind: edgeKindLabel(aggregate.kind, t),
            })
          : safeNodeName(node, locale),
      ];
    }),
  );
  return (
    <section
      className="archive-relations"
      aria-label={t("graphArchiveRelations")}
    >
      {edgeKinds.map((kind) => {
        const edges = graph.edges.filter((edge) => edge.kind === kind);
        return (
          <details
            key={kind}
            open={edges.length > 0 && edges.length <= 8}
            data-edge-kind={kind}
          >
            <summary>
              {edgeKindLabel(kind, t)} · {edges.length}
            </summary>
            {edges.length === 0 ? (
              <p className="muted">{t("graphNoRelations")}</p>
            ) : (
              <ul>
                {edges.map((edge, index) => (
                  <li
                    key={`${String(index)}:${edge.event_id ?? edge.assertion?.id ?? ""}`}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        onSelect(edge.source);
                      }}
                    >
                      {names.get(edge.source)}
                    </button>
                    <span
                      className={`archive-relation-rule ${kind}`}
                      aria-hidden="true"
                    />
                    <span>
                      {kind === "catalog"
                        ? catalogLinkLabel(edge.link_type ?? edge.operator, t)
                        : edge.operator}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        onSelect(edge.target);
                      }}
                    >
                      {names.get(edge.target)}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </details>
        );
      })}
    </section>
  );
}
