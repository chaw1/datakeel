import { useState } from "react";

import { requireSuccess } from "../../api/client";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { bytes } from "../../lib/format";
import { useResource } from "../../lib/useResource";
import { objectHref } from "../object/navigation";

import { ReleaseReconciliation } from "./ReleaseReconciliation";

import type { components } from "../../api/generated";

type Release = components["schemas"]["ReleaseView"];
type Files = components["schemas"]["ReleaseFiles"];

export function ReleaseDetail({ releaseId }: { releaseId: string }) {
  const { t } = useI18n();
  const base = `/api/releases/${encodeURIComponent(releaseId)}`;
  const detail = useResource<Release>(base);
  const [offset, setOffset] = useState(0);
  const files = useResource<Files>(
    `${base}/files?offset=${String(offset)}&limit=50`,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function download() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${base}/export`, { method: "POST" });
      await requireSuccess(response);
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${detail.value?.tag ?? releaseId}.tar.gz`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="release-detail" aria-label={t("releaseDetail")}>
      <ResourceState {...detail} onRetry={detail.reload} />
      {detail.value && (
        <>
          <h4>{detail.value.tag}</h4>
          <p>{detail.value.notes}</p>
          <dl className="version-summary">
            <div>
              <dt>{t("releaseSourceVersion")}</dt>
              <dd>
                <a
                  href={objectHref({
                    kind: "version",
                    id: detail.value.version_id,
                    datasetId: detail.value.dataset_id,
                  })}
                >
                  {detail.value.version_id}
                </a>
              </dd>
            </div>
            <div>
              <dt>{t("releaseManifestHash")}</dt>
              <dd>
                <code>{detail.value.manifest_sha256}</code>
              </dd>
            </div>
            <div>
              <dt>{t("releaseTotalBytes")}</dt>
              <dd>{bytes(detail.value.total_bytes)}</dd>
            </div>
          </dl>
          <button
            className="button"
            disabled={busy}
            onClick={() => void download()}
          >
            {t("releaseExport")}
          </button>
          {error && (
            <p role="alert" className="error-banner">
              {error}
            </p>
          )}
          <ResourceState {...files} onRetry={files.reload} />
          {files.value && (
            <>
              <details>
                <summary>{t("releaseFrozenFiles")}</summary>
                <pre>{JSON.stringify(files.value.files, null, 2)}</pre>
              </details>
              <div className="version-controls">
                <button
                  className="button subtle"
                  disabled={!offset || files.loading}
                  onClick={() => {
                    setOffset(Math.max(0, offset - 50));
                  }}
                >
                  {t("previous")}
                </button>
                <span>{t("versionOffset", { offset: offset + 1 })}</span>
                <button
                  className="button subtle"
                  disabled={files.value.next_offset === null || files.loading}
                  onClick={() => {
                    setOffset(files.value?.next_offset ?? offset);
                  }}
                >
                  {t("next")}
                </button>
              </div>
            </>
          )}
          <ReleaseReconciliation releaseId={releaseId} />
        </>
      )}
    </article>
  );
}
