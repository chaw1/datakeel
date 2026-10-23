import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { objectHref } from "../object/navigation";

import type { Version } from "../../api/types";

export function Versions({
  versions,
  datasetId,
}: {
  versions: Version[];
  datasetId?: string;
}) {
  const { t, locale } = useI18n();

  return (
    <div className="version-list">
      {versions.length ? (
        versions.map((version, index) => (
          <article className="version-row" key={version.id}>
            <div className="version-icon">
              <Icon name="layers" />
            </div>
            <div className="version-content">
              <div className="version-title">
                <h3>
                  <a
                    href={objectHref({
                      kind: "version",
                      id: version.id,
                      datasetId,
                      tab: "facts",
                    })}
                  >
                    {t("version")} {versions.length - index}
                  </a>
                </h3>
                {index === 0 && (
                  <span className="badge green">{t("latestLabel")}</span>
                )}
              </div>
              <p className="mono small">{version.id}</p>
              <div className="muted small">
                {date(version.created_at, locale)} · {version.file_count}{" "}
                {t("files", { count: version.file_count })}{" "}
              </div>
              {
                <details>
                  <summary>{t("inspectManifestSnapshot")}</summary>
                  <pre>{JSON.stringify(version.manifest, null, 2)}</pre>
                </details>
              }
            </div>
          </article>
        ))
      ) : (
        <div className="empty-state">
          <p>{t("aVersionWillAppearAfterTheDatasetIsImported")}</p>
        </div>
      )}
    </div>
  );
}
