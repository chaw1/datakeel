import { classifications, assetStatuses } from "../../api/dataAssets";
import { useI18n } from "../../i18n/useI18n";
import { date, display } from "../../lib/format";

import type { DataAssetCard } from "../../api/dataAssets";

export function AssetSummary({
  card,
  expanded = false,
}: {
  card: DataAssetCard;
  expanded?: boolean;
}) {
  const { t, locale } = useI18n();
  const { asset } = card;
  const definition = asset.definition;
  const name =
    locale === "en" && definition.name_en
      ? definition.name_en
      : definition.name;
  const classification =
    classifications.find(
      ([value]) => value === definition.classification,
    )?.[1] ?? "assetInternal";
  const values = [
    [
      "qualityScore",
      card.quality_score == null
        ? t("assetNoValue")
        : card.quality_score.toFixed(1),
    ],
    ["assetUsageCount", card.usage_count],
    ["assetUserCount", card.user_count],
    ["assetDownstreamCount", card.downstream_count],
    ["assetUpdated", date(card.updated_at ?? undefined, locale)],
  ] as const;
  return (
    <article className="asset-summary">
      <div className="asset-title-row">
        <h2>{name}</h2>
        <span className="badge">{t(classification)}</span>
        <span className="badge">{t(assetStatuses[asset.status])}</span>
      </div>
      <p>{definition.description}</p>
      <p className="muted">
        {t("assetOwner")}: {definition.owner}
      </p>
      <div className="asset-tags">
        {definition.tags.map((tag) => (
          <span className="badge" key={tag}>
            {tag}
          </span>
        ))}
      </div>
      <dl className="detail-grid">
        {values.map(([key, value]) => (
          <div key={key}>
            <dt>{t(key)}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {expanded && (
        <>
          <dl className="detail-grid">
            <div>
              <dt>{t("assetRevision")}</dt>
              <dd>{asset.revision}</dd>
            </div>
            <div>
              <dt>{t("assetFreshnessAge")}</dt>
              <dd>
                {card.freshness_seconds == null
                  ? t("assetNoValue")
                  : (card.freshness_seconds / 3600).toFixed(1)}
              </dd>
            </div>
          </dl>
          {definition.synonyms.length ? (
            <p>
              {t("assetSynonyms")}: {definition.synonyms.join(", ")}
            </p>
          ) : null}
          {definition.scenarios.length ? (
            <section>
              <h3>{t("assetScenarios")}</h3>
              <ul>
                {definition.scenarios.map((value) => (
                  <li key={value}>{value}</li>
                ))}
              </ul>
            </section>
          ) : null}
          {definition.instructions && (
            <section>
              <h3>{t("assetInstructions")}</h3>
              <p className="asset-prose">{definition.instructions}</p>
            </section>
          )}
          {definition.sample && (
            <section>
              <h3>{t("assetSample")}</h3>
              <pre>{definition.sample}</pre>
            </section>
          )}
          {card.quality_trend.length > 0 && (
            <section>
              <h3>{t("assetQualityTrend")}</h3>
              <ol className="asset-trend">
                {card.quality_trend.map((point) => (
                  <li key={point.occurred_at}>
                    {date(point.occurred_at, locale)} · {point.score.toFixed(1)}
                  </li>
                ))}
              </ol>
            </section>
          )}
          {(
            [
              ["assetUpstream", card.upstream],
              ["assetDownstreamRefs", card.downstream],
              ["assetRelatedMetrics", card.related_metrics],
            ] as const
          ).map(([key, refs]) => (
            <section key={key}>
              <h3>{t(key)}</h3>
              {refs.length ? (
                <ul>
                  {refs.map((ref) => (
                    <li key={`${ref.asset_type}:${ref.asset_id}`}>
                      {ref.asset_id}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">{t("assetNoValue")}</p>
              )}
            </section>
          ))}
          {card.version_release != null && (
            <section>
              <h3>{t("assetVersionRelease")}</h3>
              <pre>{display(card.version_release)}</pre>
            </section>
          )}
          {card.standard_coverage != null && (
            <p>
              {t("assetStandardCoverage")}: {card.standard_coverage}
            </p>
          )}
        </>
      )}
    </article>
  );
}
