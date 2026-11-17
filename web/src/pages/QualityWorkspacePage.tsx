import { EmptyState, PageHeader, Surface } from "../components/ui";
import { objectHref } from "../features/object/navigation";
import { useI18n } from "../i18n/useI18n";

import type { DatasetSummary } from "../app/useDashboard";

export function QualityWorkspacePage({
  datasets,
  alertsOnly,
}: {
  datasets: DatasetSummary[];
  alertsOnly: boolean;
}) {
  const { t } = useI18n();
  const shown = datasets.filter(
    (dataset) =>
      !alertsOnly ||
      (dataset.quality_score != null && dataset.quality_score < 60),
  );
  return (
    <>
      <PageHeader
        title={t("qualityDatasets", { count: shown.length })}
        actions={
          <label>
            <input
              type="checkbox"
              checked={alertsOnly}
              onChange={(event) => {
                window.location.hash = event.target.checked
                  ? "/quality?filter=alerts"
                  : "/quality";
              }}
            />
            {t("qualityAlertFilter")}
          </label>
        }
      />
      <Surface className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("sourceDataset")}</th>
              <th>{t("qualityScore")}</th>
              <th>{t("detailsLink")}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((dataset) => (
              <tr key={dataset.id}>
                <td>{dataset.name}</td>
                <td>
                  {dataset.quality_score == null
                    ? t("scoreNotMeasured")
                    : dataset.quality_score.toFixed(1)}
                </td>
                <td>
                  <a
                    className="text-button"
                    href={objectHref({
                      kind: "dataset",
                      id: dataset.id,
                      tab: "quality",
                    })}
                  >
                    {t("detailsLink")}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Surface>
      {!shown.length && (
        <EmptyState
          title={t("noQualityAlerts")}
          action={
            alertsOnly ? (
              <a className="text-button" href="#/quality">
                {t("clearFilter")}
              </a>
            ) : undefined
          }
        />
      )}
    </>
  );
}
