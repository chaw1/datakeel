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
    <section className="card">
      <div className="card-heading">
        <div>
          <h2>{t("versionHistory")}</h2>
          <p>
            {t(
              "eachVersionPreservesACompleteFileManifestAndContentHashes",
            )}{" "}
          </p>
        </div>
        <span className="badge gray">
          {data.versions.length}{" "}
          {t("snapshots", { count: data.versions.length })}{" "}
        </span>
      </div>
      <VersionWorkspace versions={data.versions} datasetId={selectedId} />
    </section>
  );
}
