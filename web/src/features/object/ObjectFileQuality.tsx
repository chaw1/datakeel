import { useI18n } from "../../i18n/useI18n";

import { objectHref } from "./navigation";

import type { ObjectData } from "../../api/objects";

export function ObjectFileQuality({ data }: { data: ObjectData }) {
  const { t } = useI18n();
  const sample = data.samples.at(0);
  return (
    <section
      className="object-source-detail object-file-quality"
      aria-label={t("objQuality")}
    >
      <h2>{t("evQuality")}</h2>
      {sample ? (
        <>
          <p>{sample.filename}</p>
          <dl>
            <dt>{t("objQuality")}</dt>
            <dd>
              <strong>{sample.quality_score.toFixed(1)}</strong>
            </dd>
            <dt>{t("evVersion")}</dt>
            <dd>
              <a
                href={objectHref({
                  kind: "version",
                  id: sample.source_version,
                  datasetId: sample.dataset_id,
                  tab: "facts",
                })}
              >
                <code>{sample.source_version}</code>
              </a>
            </dd>
          </dl>
          <details>
            <summary>{t("objSourceRecord")}</summary>
            <pre>
              {JSON.stringify(
                {
                  asset_ref: sample.asset_ref,
                  source_version: sample.source_version,
                  quality_score: sample.quality_score,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      ) : (
        <p className="muted">{t("objNoSource")}</p>
      )}
    </section>
  );
}
