import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";
import { date, display } from "../../lib/format";
import { safeNodeName } from "../graph/archiveModel";
import { StateBadge } from "../tasks/StateBadge";

import { catalogLinkLabel } from "./catalogLabels";

import type { GraphEdge, GraphNode, LineageEvent } from "../../api/types";

export function LineageDetails({
  node,
  nodes,
  edges,
  events,
  onClose,
}: {
  node: GraphNode;
  nodes: GraphNode[];
  edges: GraphEdge[];
  events: LineageEvent[];
  onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const name = (id: string) => {
    const item = nodes.find((entry) => entry.id === id);
    return item ? safeNodeName(item, locale) : t("asset");
  };
  const semantic = edges.filter((edge) => edge.kind === "semantic");
  const catalog = edges.filter((edge) => edge.kind === "catalog");
  return (
    <section className="event-panel" aria-label={t("lineageEventDetails")}>
      <div className="section-heading">
        <div>
          <span className="eyebrow">{t("assetDetails")}</span>
          <h3>{safeNodeName(node, locale)}</h3>
        </div>
        <button
          className="icon-button"
          aria-label={t("closeEventDetails")}
          onClick={onClose}
        >
          <Icon name="close" />
        </button>
      </div>
      {node.quarantined && (
        <span className="badge amber">{t("quarantined")}</span>
      )}
      {node.deleted && <span className="badge gray">{t("deletedFile")}</span>}
      {catalog.length > 0 && (
        <>
          <h4>{t("catalogRelations")}</h4>
          <ul className="catalog-relations">
            {catalog.map((edge) => (
              <li key={`${edge.source}:${edge.link_type ?? ""}:${edge.target}`}>
                <strong>{catalogLinkLabel(edge.link_type ?? "", t)}</strong>
                <code>
                  {name(edge.source)} → {name(edge.target)}
                </code>
              </li>
            ))}
          </ul>
        </>
      )}
      {events.length === 0 && (
        <p className="muted">
          {t("noConnectedEventsAreAvailableForThisAsset")}
        </p>
      )}
      {events.map((event, index) => (
        <article
          className="event-detail"
          key={display(event.event_id, String(index))}
        >
          <div className="event-meta">
            <strong>
              {display(
                event.operator,
                display(event.event_type, t("lineageEvent")),
              )}
            </strong>
            <StateBadge
              state={
                event.run_state === "FAIL"
                  ? "FAILED"
                  : event.run_state || t("recorded")
              }
            />
            <span>{date(event.occurred_at, locale)}</span>
          </div>
          <p className="mono small" title={event.event_id ?? undefined}>
            {display(event.event_id).slice(0, 8)}
          </p>
          <details>
            <summary>{t("viewCompleteEvent")}</summary>
            <pre>{JSON.stringify(event, null, 2)}</pre>
          </details>
        </article>
      ))}
      {semantic.length > 0 && <h4>{t("semanticRelations")}</h4>}
      {semantic.map((edge) => (
        <article
          className="event-detail semantic-detail"
          key={edge.assertion?.id}
        >
          <div className="event-meta">
            <strong>{edge.link_type}</strong>
            <span>
              {name(edge.source)} ↔ {name(edge.target)}
            </span>
            {edge.assertion && (
              <span className="badge gray">{t(edge.assertion.status)}</span>
            )}
          </div>
          <p className="mono small">
            {t("assertionSource")}: {edge.assertion?.extractor.id} ·{" "}
            {edge.assertion?.extractor.version}
          </p>
          <p className="small">
            {t("distance")}: {edge.assertion?.distance}
          </p>
          <details>
            <summary>{t("viewAssertion")}</summary>
            <pre>{JSON.stringify(edge.assertion, null, 2)}</pre>
          </details>
        </article>
      ))}
    </section>
  );
}
