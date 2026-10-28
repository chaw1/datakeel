import { useState } from "react";

import { createSplit, trainingPath } from "../../api/training";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useResource } from "../../lib/useResource";

import { TrainingDistribution } from "./TrainingDistribution";
import { TrainingExport } from "./TrainingExport";
import { TrainingForm } from "./TrainingForm";
import { TrainingLeakage } from "./TrainingLeakage";
import { TrainingMembers } from "./TrainingMembers";

import type { SplitRequest, SplitSet } from "../../api/training";

export function TrainingWorkspace({
  datasetId,
  versionId,
}: {
  datasetId: string;
  versionId: string;
}) {
  const { t, locale } = useI18n();
  const resource = useResource<SplitSet[]>(
    `${trainingPath(datasetId, versionId)}/splits`,
  );
  const [selectedId, setSelectedId] = useState("");
  const [compareId, setCompareId] = useState("");
  const [preview, setPreview] = useState<SplitSet | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const splits = resource.value ?? [];
  const selected =
    splits.find((split) => split.id === selectedId) ?? splits.at(0);
  const active = preview ?? selected;
  const comparison = splits.find(
    (split) => split.id === compareId && split.id !== active?.id,
  );
  async function generate(request: SplitRequest, previewOnly: boolean) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const created = await createSplit(
        datasetId,
        versionId,
        request,
        previewOnly,
      );
      setCompareId("");
      if (previewOnly) setPreview(created);
      else {
        setPreview(null);
        setSelectedId(created.id);
        resource.reload();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="training-workspace">
      <TrainingForm
        busy={busy}
        onSubmit={(request, previewOnly) => void generate(request, previewOnly)}
        onChange={() => {
          setPreview(null);
        }}
      />
      <ResourceState
        loading={resource.loading || busy}
        error={error || resource.error}
        onRetry={resource.reload}
      />
      {!resource.loading && !splits.length && (
        <p className="muted">{t("trainingEmpty")}</p>
      )}
      {!!splits.length && (
        <div className="training-controls">
          <label>
            {t("trainingSaved")}
            <select
              value={preview ? "" : (selected?.id ?? "")}
              onBlur={(event) => {
                if (event.target.value) {
                  setSelectedId(event.target.value);
                  setPreview(null);
                }
              }}
              onChange={(event) => {
                setSelectedId(event.target.value);
                setPreview(null);
                setCompareId("");
              }}
            >
              {preview && <option value="">{t("trainingPreview")}</option>}
              {splits.map((split) => (
                <option key={split.id} value={split.id}>
                  {split.request.name} · {split.members.length}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("trainingCompare")}
            <select
              value={comparison?.id ?? ""}
              onBlur={(event) => {
                setCompareId(event.target.value);
              }}
              onChange={(event) => {
                setCompareId(event.target.value);
              }}
            >
              <option value="">{t("trainingNoComparison")}</option>
              {splits
                .filter((split) => split.id !== active?.id)
                .map((split) => (
                  <option key={split.id} value={split.id}>
                    {split.request.name}
                  </option>
                ))}
            </select>
          </label>
          <button className="button subtle" onClick={resource.reload}>
            {t("refresh")}
          </button>
        </div>
      )}
      {active && (
        <article className="training-detail">
          <p className="muted">
            {t(preview ? "trainingPreviewHint" : "trainingImmutableHint")}
          </p>
          {!preview && (
            <p className="small muted">
              <code>{active.id}</code> · {date(active.created_at, locale)}
            </p>
          )}
          {!!comparison && <h4>{t("trainingComparison")}</h4>}
          <div className={comparison ? "training-comparison" : undefined}>
            {comparison && (
              <div>
                <h5>{t("trainingBefore")}</h5>
                <TrainingDistribution split={comparison} />
              </div>
            )}
            <div>
              {comparison && <h5>{t("trainingAfter")}</h5>}
              <TrainingDistribution split={active} />
            </div>
          </div>
          <details>
            <summary>{t("trainingConfig")}</summary>
            <pre>{JSON.stringify(active.request, null, 2)}</pre>
          </details>
          <TrainingMembers key={`members:${active.id}`} split={active} />
          {!preview && (
            <>
              <TrainingLeakage key={`leakage:${active.id}`} split={active} />
              <TrainingExport key={`export:${active.id}`} split={active} />
            </>
          )}
        </article>
      )}
    </div>
  );
}
