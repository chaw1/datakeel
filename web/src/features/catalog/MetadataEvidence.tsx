import { useI18n } from "../../i18n/useI18n";

import type { CatalogObject } from "../../api/catalog";

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : value && typeof value === "object"
      ? JSON.stringify(value)
      : "";
}

function contributions(item: CatalogObject) {
  const combined = record(item.properties?.integrations);
  const entries = Object.entries(combined ?? {}).flatMap(([scope, value]) => {
    const integration = record(value);
    return integration ? [{ scope, integration }] : [];
  });
  const primary = record(item.properties?.integration);
  return entries.length
    ? entries
    : primary
      ? [{ scope: "", integration: primary }]
      : [];
}

export function MetadataEvidence({ item }: { item: CatalogObject }) {
  const { t } = useI18n();
  const entries = contributions(item);
  const integration =
    record(item.properties?.integration) ?? entries.at(0)?.integration;
  if (!integration) return null;
  const details = record(integration.details) ?? {};
  const allDetails = entries.map(
    ({ integration: value }) => record(value.details) ?? {},
  );
  const successes = allDetails
    .flatMap((value) => {
      const success = value.last_success ?? value.last_successful_run;
      return typeof success === "string" && Number.isFinite(Date.parse(success))
        ? [success]
        : [];
    })
    .sort((left, right) => Date.parse(right) - Date.parse(left));
  const fields = [
    ["metadataUniqueId", integration.unique_id],
    ["metadataDescription", integration.description],
    ["catOwner", integration.owner],
    [
      "metadataTags",
      Array.isArray(integration.tags) ? integration.tags.join(", ") : "",
    ],
    [
      "metadataSchedule",
      details.schedule ?? allDetails.find((value) => value.schedule)?.schedule,
    ],
    [
      "metadataRunState",
      details.latest_state ??
        details.state ??
        allDetails.find((value) => value.state)?.state,
    ],
    ["metadataLastSuccess", successes[0]],
  ] as const;
  const deleted =
    item.properties?.source_deleted === true ||
    (item.properties?.source_deleted === undefined &&
      entries.length === 1 &&
      integration.source_deleted === true);
  const unmatched = allDetails.some((value) => value.unmatched_source === true);
  return (
    <section className="metadata-evidence" aria-label={t("metadataEvidence")}>
      <h3>{t("metadataEvidence")}</h3>
      {deleted && <p className="badge warning">{t("metadataDeleted")}</p>}
      {unmatched && (
        <p className="badge" title={t("metadataUnmatchedSourceHint")}>
          {t("metadataUnmatchedSource")}
        </p>
      )}
      <dl className="catalog-definition">
        {fields.map(([label, value]) =>
          text(value) ? (
            <div className="metadata-fact" key={label}>
              <dt>{t(label)}</dt>
              <dd>{text(value)}</dd>
            </div>
          ) : null,
        )}
      </dl>
      <details>
        <summary>{t("metadataDetails")}</summary>
        {entries.map(({ scope, integration: source }) => (
          <section key={scope}>
            <h4>
              {text(source.system)} · {text(source.unique_id)}
            </h4>
            {source.source_deleted === true && (
              <p>
                {t("metadataContributionDeleted", {
                  system: text(source.system),
                })}
              </p>
            )}
            <pre>{JSON.stringify(source.details, null, 2)}</pre>
          </section>
        ))}
      </details>
    </section>
  );
}
