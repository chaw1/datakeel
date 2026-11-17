import { ResourceState } from "../../components/ResourceState";
import { Badge } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";
import { objectHref } from "../object/navigation";

import type { DatasheetDocument } from "../../api/datasheets";
import type { components } from "../../api/generated";
import type { Version } from "../../api/types";

export function DeliveryVersionChanges({
  datasetId,
  version,
  baseline,
}: {
  datasetId: string;
  version: Version;
  baseline?: Version;
}) {
  const { t } = useI18n();
  const path = `/api/datasets/${encodeURIComponent(datasetId)}`;
  const diff = useResource<components["schemas"]["VersionDiff"]>(
    baseline
      ? `${path}/diff?${new URLSearchParams({ before: baseline.id, after: version.id, limit: "1" }).toString()}`
      : null,
  );
  const sheets = useResource<DatasheetDocument[]>(`${path}/datasheets`);
  const current = sheets.value?.some((item) => item.version_id === version.id);
  return (
    <div className="delivery-version-changes">
      <ResourceState {...diff} onRetry={diff.reload} />
      {diff.value && (
        <dl className="delivery-diff">
          <div>
            <dt>{t("versionAdded")}</dt>
            <dd>{diff.value.counts.added}</dd>
          </div>
          <div>
            <dt>{t("versionRemoved")}</dt>
            <dd>{diff.value.counts.removed}</dd>
          </div>
          <div>
            <dt>{t("versionContentChanged")}</dt>
            <dd>{diff.value.counts.content_changed}</dd>
          </div>
          <div>
            <dt>{t("versionMetadataChanged")}</dt>
            <dd>{diff.value.counts.metadata_changed}</dd>
          </div>
        </dl>
      )}
      <ResourceState {...sheets} onRetry={sheets.reload} />
      {sheets.value && (
        <div className="delivery-datasheet">
          <Badge tone={current ? "ok" : "neutral"}>
            {t(
              current
                ? "deliveryDatasheetCurrent"
                : sheets.value.length
                  ? "deliveryDatasheetStale"
                  : "deliveryDatasheetMissing",
            )}
          </Badge>
          <a
            className="text-button"
            href={objectHref({
              kind: "dataset",
              id: datasetId,
              tab: "datasheets",
              versionId: version.id,
            })}
          >
            {t("deliveryDatasheetLink")}
          </a>
        </div>
      )}
    </div>
  );
}
