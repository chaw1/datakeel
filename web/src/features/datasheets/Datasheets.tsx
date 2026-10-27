import { useState } from "react";

import { get } from "../../api/client";
import { generateDatasheet, publishDatasheet } from "../../api/datasheets";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useResource } from "../../lib/useResource";
import { ApprovalSheet } from "../approvals/ApprovalSheet";
import { objectHref } from "../object/navigation";

import { DatasheetChanges } from "./DatasheetChanges";
import { DatasheetControls } from "./DatasheetControls";
import { DatasheetView } from "./DatasheetView";
import "./datasheets.css";

import type { DatasheetDocument } from "../../api/datasheets";
import type { ActionPlan, Version } from "../../api/types";

export function Datasheets({
  datasetId,
  versions,
  initialVersionId,
}: {
  datasetId: string;
  versions: Version[];
  initialVersionId?: string;
}) {
  const { t, locale } = useI18n();
  const [versionId, setVersionId] = useState(
    initialVersionId ?? versions.at(0)?.id ?? "",
  );
  const [liveVersions, setLiveVersions] = useState<Version[] | null>(null);
  const [language, setLanguage] =
    useState<DatasheetDocument["language"]>(locale);
  const [mode, setMode] = useState<DatasheetDocument["mode"]>("template");
  const [provider, setProvider] = useState<"fake" | "openai" | "anthropic">(
    "fake",
  );
  const [model, setModel] = useState("fake-demo");
  const resource = useResource<DatasheetDocument[]>(
    `/api/datasets/${encodeURIComponent(datasetId)}/datasheets`,
  );
  const documents = resource.value ?? [];
  const [selectedId, setSelectedId] = useState("");
  const [compareId, setCompareId] = useState("");
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const matching = documents.filter(
    (item) => item.version_id === versionId && item.language === language,
  );
  const sheet =
    matching.find((item) => item.id === selectedId) ?? matching.at(0);
  const comparison = documents.find(
    (item) => item.id === compareId && item.id !== sheet?.id,
  );
  function refresh() {
    setError("");
    resource.reload();
  }
  async function prepare(publish = false, latest = false) {
    if (busy || !versionId) return;
    setBusy(true);
    setError("");
    setPlan(null);
    setTaskId(null);
    try {
      let targetVersionId = versionId;
      if (latest) {
        const current = await get<Version[]>(
          `/api/datasets/${encodeURIComponent(datasetId)}/versions`,
        );
        current.sort(
          (left, right) =>
            right.created_at - left.created_at ||
            right.id.localeCompare(left.id),
        );
        setLiveVersions(current);
        const newest = current.at(0);
        if (!newest) throw new Error(t("datasheetNoVersions"));
        targetVersionId = newest.id;
        changeVersion(targetVersionId);
      }
      setPlan(
        publish && sheet
          ? await publishDatasheet(sheet.id)
          : await generateDatasheet(
              datasetId,
              targetVersionId,
              language,
              mode,
              {
                provider,
                model,
              },
            ),
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : t("datasheetFailure"),
      );
    } finally {
      setBusy(false);
    }
  }
  function changeVersion(value: string) {
    if (value === versionId) return;
    setVersionId(value);
    setSelectedId("");
    setCompareId("");
    setPlan(null);
    setTaskId(null);
  }
  return (
    <section className="datasheets" aria-label={t("datasheets")}>
      <div className="card-heading">
        <div>
          <h2>{t("datasheets")}</h2>
          <p>{t("datasheetDescription")}</p>
        </div>
        <button className="button" onClick={refresh}>
          {t("datasheetRefresh")}
        </button>
      </div>
      <DatasheetControls
        versions={liveVersions ?? versions}
        versionId={versionId}
        language={language}
        mode={mode}
        provider={provider}
        model={model}
        busy={busy}
        existing={!!sheet}
        onVersion={changeVersion}
        onLanguage={(value) => {
          if (value === language) return;
          setLanguage(value);
          setCompareId("");
          setPlan(null);
          setTaskId(null);
        }}
        onMode={(value) => {
          if (value === mode) return;
          setMode(value);
          setPlan(null);
        }}
        onProvider={(value) => {
          if (value === provider) return;
          setProvider(value);
          setModel(value === "fake" ? "fake-demo" : "");
          setPlan(null);
        }}
        onModel={(value) => {
          setModel(value);
          setPlan(null);
        }}
        onGenerate={() => {
          void prepare();
        }}
      />
      <ResourceState
        loading={resource.loading}
        error={error || resource.error}
        onRetry={refresh}
      />
      {!versions.length && (
        <p className="empty-state">{t("datasheetNoVersions")}</p>
      )}
      {!!versions.length && !resource.loading && !sheet && (
        <p className="empty-state">{t("datasheetNoDocuments")}</p>
      )}
      {plan && (
        <ApprovalSheet
          key={plan.id}
          plan={plan}
          onResolved={(run) => {
            setSelectedId("");
            setTaskId(run?.task_id ?? null);
            refresh();
          }}
          onOpenReceipt={(target) => {
            window.location.hash = objectHref({
              kind: "dataset",
              id: target.datasetId ?? datasetId,
              tab: "relations",
              eventId: target.eventId,
            });
          }}
        />
      )}
      {taskId && (
        <p role="status">
          {t("datasheetQueued")}{" "}
          <a href={`#/runs?type=pipeline&run=${encodeURIComponent(taskId)}`}>
            {t("datasheetTask", { id: taskId })}
          </a>
        </p>
      )}
      {sheet && (
        <>
          <div className="datasheet-controls">
            <label>
              {t("datasheetHistory")}
              <select
                aria-label={t("datasheetHistory")}
                value={sheet.id}
                onBlur={(event) => {
                  setSelectedId(event.target.value);
                }}
                onChange={(event) => {
                  setSelectedId(event.target.value);
                  setPlan(null);
                }}
              >
                {matching.map((item) => (
                  <option key={item.id} value={item.id}>
                    {date(item.created_at, locale)} · {item.id.slice(0, 8)} ·{" "}
                    {t(
                      item.published ? "datasheetPublished" : "datasheetDraft",
                    )}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("datasheetCompare")}
              <select
                aria-label={t("datasheetCompare")}
                value={comparison?.id ?? ""}
                onBlur={(event) => {
                  setCompareId(event.target.value);
                }}
                onChange={(event) => {
                  setCompareId(event.target.value);
                }}
              >
                <option value="">{t("datasheetNoComparison")}</option>
                {documents
                  .filter(
                    (item) =>
                      item.id !== sheet.id && item.language === language,
                  )
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.version_id} · {date(item.created_at, locale)} ·{" "}
                      {item.id.slice(0, 8)}
                    </option>
                  ))}
              </select>
            </label>
            <button
              className="button"
              disabled={busy || sheet.published}
              onClick={() => {
                void prepare(true);
              }}
            >
              {t("datasheetPublish")}
            </button>
            {sheet.stale && (
              <button
                className="button primary"
                disabled={busy}
                onClick={() => {
                  void prepare(false, true);
                }}
              >
                {t("datasheetRegenerateLatest")}
              </button>
            )}
          </div>
          {comparison && (
            <DatasheetChanges
              key={`${comparison.id}:${sheet.id}`}
              before={comparison}
              after={sheet}
            />
          )}
          <div className={comparison ? "datasheet-comparison" : undefined}>
            {comparison && (
              <section>
                <h3>{t("datasheetBefore")}</h3>
                <DatasheetView sheet={comparison} downloads={false} />
              </section>
            )}
            <section>
              {comparison && <h3>{t("datasheetAfter")}</h3>}
              <DatasheetView sheet={sheet} />
            </section>
          </div>
        </>
      )}
    </section>
  );
}
