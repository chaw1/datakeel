import { useI18n } from "../../i18n/useI18n";

import type { AskMetric } from "../../api/ask";

export function MetricEvidence({ metric }: { metric: AskMetric }) {
  const { t } = useI18n();
  const definition = metric.definition;
  return (
    <section className="ask-metric" aria-label={t("askMetric")}>
      <div className="ask-section-heading">
        <span className="eyebrow">{t("askMetric")}</span>
        <span className="badge green">
          {t("askVersion", { version: definition.version })}
        </span>
      </div>
      <h2>{definition.name}</h2>
      <p>{definition.description}</p>
      <dl className="ask-facts">
        <div>
          <dt>{t("askOwner")}</dt>
          <dd>{definition.owner}</dd>
        </div>
        <div>
          <dt>{t("askMeasure")}</dt>
          <dd>
            <code>{`${definition.measure.aggregation}(${definition.measure.column})`}</code>
          </dd>
        </div>
        <div>
          <dt>{t("askFilters")}</dt>
          <dd>
            {definition.filters?.length ? (
              <ul className="ask-id-list">
                {definition.filters.map((filter, index) => (
                  <li key={`${filter.column}-${String(index)}`}>
                    <code>{`${filter.column} ${filter.op} ${JSON.stringify(filter.value)}`}</code>
                  </li>
                ))}
              </ul>
            ) : (
              t("askNoFilters")
            )}
          </dd>
        </div>
      </dl>
      <h3>{t("askCaveats")}</h3>
      {definition.caveats?.length ? (
        <ul className="ask-caveats">
          {definition.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      ) : (
        <p className="ask-muted">{t("askNoCaveats")}</p>
      )}
      <a
        className="ask-history"
        href={`/api/catalog/metrics/${encodeURIComponent(definition.id)}/history`}
        target="_blank"
        rel="noreferrer"
      >
        {t("askHistory")}
      </a>
    </section>
  );
}
