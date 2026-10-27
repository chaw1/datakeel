import { useState } from "react";

import { annotationPath } from "../../api/annotation";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useResource } from "../../lib/useResource";

import { AnnotationAgreement } from "./AnnotationAgreement";
import { AnnotationFindings } from "./AnnotationFindings";
import { AnnotationImport } from "./AnnotationImport";
import { AnnotationSampling } from "./AnnotationSampling";
import "./annotation.css";

import type { AnnotationOverview } from "../../api/annotation";

export function AnnotationQuality({
  datasetId,
  versionId,
}: {
  datasetId: string;
  versionId?: string;
}) {
  const { t, locale } = useI18n();
  const resource = useResource<AnnotationOverview>(
    annotationPath(datasetId, versionId),
  );
  const [selected, setSelected] = useState("");
  const overview = resource.value;
  const batches = overview?.batches ?? [];
  const report =
    batches.find((batch) => batch.id === selected) ?? overview?.latest;
  return (
    <div className="annotation-quality">
      <header>
        <h2>{t("annotationQuality")}</h2>
        <p>{t("annotationDescription")}</p>
      </header>
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {overview && (
        <>
          {versionId && (
            <AnnotationImport
              datasetId={datasetId}
              versionId={versionId}
              batches={batches}
              onChanged={resource.reload}
            />
          )}
          {!!batches.length && (
            <label className="annotation-form">
              {t("annotationBatch")}
              <select
                value={report?.id ?? ""}
                onChange={(event) => {
                  setSelected(event.target.value);
                }}
                onBlur={(event) => {
                  setSelected(event.target.value);
                }}
              >
                {batches.map((batch) => (
                  <option key={batch.id} value={batch.id}>
                    {batch.name} · {date(batch.created_at, locale)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {report ? (
            <>
              <AnnotationAgreement result={report.result} />
              <AnnotationSampling
                key={report.id}
                report={report}
                overview={overview}
                onChanged={resource.reload}
              />
              <AnnotationFindings report={report} />
            </>
          ) : (
            <p className="card empty-state">{t("annotationEmpty")}</p>
          )}
        </>
      )}
    </div>
  );
}
