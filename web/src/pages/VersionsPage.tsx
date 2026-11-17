import { Badge, Surface } from "../components/ui";
import { VersionWorkspace } from "../features/versions/VersionWorkspace";
import { useI18n } from "../i18n/useI18n";

import type { DatasetData } from "../api/types";

export function VersionsPage({
  data,
  selectedId,
}: {
  data: DatasetData;
  selectedId: string;
}) {
  const { t } = useI18n();
  return (
    <Surface as="section">
      <div className="card-heading">
        <div>
          <h2>{t("versionHistory")}</h2>
          <p>
            {t(
              "eachVersionPreservesACompleteFileManifestAndContentHashes",
            )}{" "}
          </p>
        </div>
        <Badge>
          {data.versions.length}{" "}
          {t("snapshots", { count: data.versions.length })}{" "}
        </Badge>
      </div>
      <VersionWorkspace versions={data.versions} datasetId={selectedId} />
    </Surface>
  );
}
