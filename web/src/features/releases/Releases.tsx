import { useState } from "react";

import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useResource } from "../../lib/useResource";

import { PublishRelease } from "./PublishRelease";
import { ReleaseDetail } from "./ReleaseDetail";

import type { components } from "../../api/generated";
import type { Version } from "../../api/types";

type Release = components["schemas"]["ReleaseView"];

export function Releases({
  versions,
  datasetId,
  onChanged,
}: {
  versions: Version[];
  datasetId: string;
  onChanged?: () => void;
}) {
  const { t, locale } = useI18n();
  const resource = useResource<Release[]>(
    `/api/datasets/${encodeURIComponent(datasetId)}/releases`,
  );
  const [selected, setSelected] = useState("");
  function changed() {
    resource.reload();
    onChanged?.();
  }
  return (
    <section aria-label={t("releaseTitle")}>
      <div className="card-heading">
        <div>
          <h3>{t("releaseTitle")}</h3>
          <p>{t("releaseFrozenHint")}</p>
        </div>
        <button className="button subtle" onClick={resource.reload}>
          {t("refresh")}
        </button>
      </div>
      <PublishRelease
        versions={versions}
        datasetId={datasetId}
        onChanged={changed}
      />
      <ResourceState {...resource} onRetry={resource.reload} />
      {resource.value && !resource.value.length && <p>{t("releaseEmpty")}</p>}
      <ul className="release-list">
        {resource.value?.map((release) => (
          <li key={release.id}>
            <button
              className="text-button"
              aria-expanded={selected === release.id}
              onClick={() => {
                setSelected(selected === release.id ? "" : release.id);
              }}
            >
              {release.tag}
            </button>{" "}
            <span className="muted">
              {date(release.created_at, locale)} ·{" "}
              {t("releaseFileCount", { count: release.file_count })}
            </span>
            {selected === release.id && (
              <ReleaseDetail releaseId={release.id} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
