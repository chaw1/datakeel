import { lineageHref } from "../../app/lineageNavigation";
import { useI18n } from "../../i18n/useI18n";
import { date, shortId } from "../../lib/format";
import { MetricHistory } from "../catalog/MetricHistory";

import { eventsFor } from "./descriptors";
import { objectHref } from "./navigation";

import type { ObjectTarget } from "./navigation";
import type { ObjectData } from "../../api/objects";

export function ObjectHistory({
  data,
  target,
  reload,
}: {
  data: ObjectData;
  target: ObjectTarget;
  reload: () => void;
}) {
  const { t } = useI18n();
  const events = eventsFor(data);
  return (
    <section className="object-history" aria-label={t("objHistory")}>
      {data.metricHistory && data.metric && (
        <MetricHistory
          key={data.metricHistory.metric_id}
          history={data.metricHistory}
          currentVersion={data.metric.definition.version}
          onChanged={reload}
          onOpenReceipt={(next) => {
            window.location.hash = lineageHref(next);
          }}
        />
      )}
      {data.metricHistory?.audit.map((audit) => (
        <article
          id={`object-audit-${audit.event_id}`}
          className={`object-event ${target.eventId === audit.event_id ? "is-focused" : ""}`}
          key={audit.event_id}
        >
          <time>{date(audit.created_at)}</time>
          <div>
            <strong>{audit.action_type}</strong>
            <p>
              {audit.actor} · {audit.from_version} → {audit.to_version}
            </p>
            <details>
              <summary>{t("objRawEvent")}</summary>
              <pre>{JSON.stringify(audit, null, 2)}</pre>
            </details>
          </div>
        </article>
      ))}
      {!events.length && <p className="empty-state">{t("objNoEvents")}</p>}
      {events.map((event, index) => (
        <article
          id={`object-event-${event.event_id ?? String(index)}`}
          className={`object-event ${target.eventId === event.event_id ? "is-focused" : ""}`}
          key={event.event_id ?? String(index)}
        >
          <time>{date(event.occurred_at)}</time>
          <div>
            <strong>{event.operator}</strong>
            <p>
              {event.event_type} · {event.run_state} · {event.on_behalf_of}
            </p>
            <div className="object-event-assets">
              {[...(event.inputs ?? []), ...(event.outputs ?? [])]
                .filter(
                  (ref) =>
                    ref.asset_type === "dataset" ||
                    ref.asset_type === "file" ||
                    ref.asset_type === "version" ||
                    ref.asset_type === "action_run",
                )
                .map((ref, index) => (
                  <a
                    key={`${ref.asset_id}:${String(index)}`}
                    href={objectHref({
                      kind: ref.asset_type as
                        "dataset" | "file" | "version" | "action_run",
                      id: ref.asset_id,
                      datasetId: data.dataset?.id,
                      tab: "facts",
                    })}
                  >
                    <code>{shortId(ref.asset_id)}</code>
                  </a>
                ))}
            </div>
            <details open={target.eventId === event.event_id}>
              <summary>{t("objRawEvent")}</summary>
              <pre>{JSON.stringify(event, null, 2)}</pre>
            </details>
          </div>
        </article>
      ))}
    </section>
  );
}
