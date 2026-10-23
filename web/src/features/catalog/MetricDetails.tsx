import { useState } from "react";

import { metricPath } from "../../api/catalog";
import { ResourceState } from "../../components/ResourceState";
import {
  localizedCatalogName,
  localizedObjectName,
} from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";
import { objectHref } from "../object/navigation";

import { MetricEditor } from "./MetricEditor";
import { serializeFilterValue } from "./values";

import type { MetricCard } from "../../api/catalog";
import type { LineageTarget } from "../../app/navigation";

export function MetricDetails({
  metricId,
  onDataChanged,
  onOpenReceipt,
  initialEditing = false,
}: {
  metricId: string;
  onDataChanged?: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
  initialEditing?: boolean;
}) {
  const { t, locale } = useI18n();
  const resource = useResource<MetricCard>(metricPath(metricId));
  const [editing, setEditing] = useState(initialEditing);
  const card = resource.value;
  const metric = card?.definition;
  return (
    <section className="card catalog-detail" aria-label={t("catDefinition")}>
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {card && metric && !resource.error && (
        <>
          <div className="section-heading">
            <div>
              <span
                className={`badge ${card.status === "resolved" ? "green" : "amber"}`}
              >
                {t(
                  card.status === "resolved" ? "catResolved" : "catUnresolved",
                )}
              </span>
              <h2>{localizedCatalogName(metric.name, t)}</h2>
              <a
                className="text-button"
                href={objectHref({ kind: "metric", id: metricId })}
              >
                {t("objOpen")}
              </a>
            </div>
            <button
              className="button subtle"
              onClick={() => {
                onOpenReceipt({ assetId: metric.id, includeCatalog: true });
              }}
            >
              {t("catLineage")}
            </button>
          </div>
          <dl className="detail-grid">
            <div>
              <dt>{t("catMetricId")}</dt>
              <dd className="mono">{metric.id}</dd>
            </div>
            <div>
              <dt>{t("version")}</dt>
              <dd>{metric.version}</dd>
            </div>
            <div>
              <dt>{t("catOwner")}</dt>
              <dd>{localizedObjectName("owner", metric.owner, locale)}</dd>
            </div>
          </dl>
          <p>{metric.description}</p>
          {card.status === "unresolved" && (
            <ul className="error-text">
              {card.reasons?.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
          <section>
            <h3>{t("catCaveats")}</h3>
            <ul>
              {metric.caveats?.map((value, index) => (
                <li key={`${String(index)}:${value}`}>{value}</li>
              ))}
            </ul>
          </section>
          <dl className="catalog-definition">
            <dt>{t("catMeasure")}</dt>
            <dd>
              <code>
                {metric.measure.aggregation}({metric.measure.column})
              </code>
            </dd>
            <dt>{t("catTime")}</dt>
            <dd>
              <code>{metric.time.column}</code>
            </dd>
            <dt>{t("catDimensions")}</dt>
            <dd>{metric.dimensions?.join(", ") || t("catNotSet")}</dd>
            <dt>{t("catFilters")}</dt>
            <dd>
              {metric.filters?.length ? (
                <ul>
                  {metric.filters.map((filter, index) => (
                    <li key={String(index)}>
                      <code>{filter.column}</code> {filter.op}{" "}
                      {serializeFilterValue(filter.value)}
                    </li>
                  ))}
                </ul>
              ) : (
                t("catAllRecords")
              )}
            </dd>
            <dt>{t("catSynonyms")}</dt>
            <dd>{metric.synonyms?.join(", ") || t("catNotSet")}</dd>
          </dl>
          <div className="catalog-toolbar">
            <a
              className="text-button"
              href={`${metricPath(metric.id)}/history`}
              target="_blank"
              rel="noreferrer"
            >
              {t("catHistory")}
            </a>
            <button
              className="button subtle"
              onClick={() => {
                setEditing(!editing);
              }}
            >
              {t(editing ? "catCloseEdit" : "catEdit")}
            </button>
          </div>
          {editing && (
            <MetricEditor
              card={card}
              onOpenReceipt={onOpenReceipt}
              onChanged={() => {
                resource.reload();
                onDataChanged?.();
              }}
            />
          )}
        </>
      )}
    </section>
  );
}
