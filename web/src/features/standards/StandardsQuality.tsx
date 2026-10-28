import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import type { components } from "../../api/generated";

const labels = {
  completeness: "completeness",
  consistency: "consistency",
  distribution: "stdValidity",
} as const;
export function StandardsQuality() {
  const { t } = useI18n();
  const resource = useResource<components["schemas"]["StandardsQuality"]>(
    "/api/standards/quality",
  );
  const quality = resource.value;
  return (
    <section className="standards-checks" aria-label={t("stdQuality")}>
      <h2>{t("stdQuality")}</h2>
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {quality && (
        <>
          <dl className="standards-summary">
            <div>
              <dt>{t("qualityScore")}</dt>
              <dd>{quality.total?.toFixed(1) ?? t("nA")}</dd>
            </div>
            <div>
              <dt>{t("stdFullyChecked")}</dt>
              <dd>
                {quality.fully_checked_columns} / {quality.mapped_columns}
              </dd>
            </div>
            <div>
              <dt>{t("stdSkippedCount")}</dt>
              <dd>{quality.skipped_rules}</dd>
            </div>
          </dl>
          <div className="catalog-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("stdQualityDimension")}</th>
                  <th>{t("qualityScore")}</th>
                  <th>{t("stdCheckedRules")}</th>
                  <th>{t("stdViolationCount")}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(quality.dimensions).map(([key, dimension]) => (
                  <tr key={key}>
                    <td>
                      {key in labels
                        ? t(labels[key as keyof typeof labels])
                        : key}
                    </td>
                    <td>{dimension.score?.toFixed(1) ?? t("nA")}</td>
                    <td>{dimension.checked_rules}</td>
                    <td>{dimension.violation_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
