import { useEffect, useState } from "react";

import { decideRelations } from "../../api/kg";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { useResource } from "../../lib/useResource";

import { KGEntities } from "./KGEntities";
import { KGEntityDrawer } from "./KGEntityDrawer";
import { KGEvaluations } from "./KGEvaluations";
import { KGExtractionForm } from "./KGExtractionForm";
import { KGFilters } from "./KGFilters";
import { KGGraphPanel } from "./KGGraphPanel";
import { KGRelationDrawer } from "./KGRelationDrawer";
import { KGRelations } from "./KGRelations";
import { KGReports } from "./KGReports";
import { useKGQuery } from "./useKGQuery";
import "./kg.css";

import type {
  KGEntity,
  KGProfile,
  KGQuery,
  KGRun,
  KGSchema,
} from "../../api/kg";
import type { Version } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

const tabs = {
  relations: "kgRelations",
  entities: "kgEntities",
  graph: "kgGraph",
  runs: "kgRuns",
  proposals: "kgProposals",
  evaluations: "kgEvaluations",
} as const;

export function KGWorkspace({
  datasetId,
  onDataChanged,
  onOpenReceipt,
}: {
  datasetId: string;
  onDataChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const [version, setVersion] = useState("");
  const [tab, setTab] = useState<keyof typeof tabs>("relations");
  const [filters, setFilters] = useState<KGQuery>({ limit: 200 });
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [relationId, setRelationId] = useState("");
  const [entity, setEntity] = useState<KGEntity | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const isComposing = useCompositionGuard();
  const versions = useResource<Version[]>(
    `/api/datasets/${encodeURIComponent(datasetId)}/versions`,
  );
  const orderedVersions = [...(versions.value ?? [])].sort(
    (a, b) => b.created_at - a.created_at,
  );
  const versionId = version || orderedVersions[0]?.id || "";
  const schemas = useResource<KGSchema[]>("/api/kg/schemas");
  const profiles = useResource<KGProfile[]>("/api/kg/profiles");
  const query = {
    ...filters,
    dataset_id: datasetId,
    version_id: versionId || null,
  };
  const resource = useKGQuery(
    "/api/kg/query",
    query,
    revision,
    !versions.loading,
  );
  const runs = useResource<KGRun[]>(
    `/api/kg/runs?${new URLSearchParams({ dataset_id: datasetId, ...(versionId ? { version_id: versionId } : {}) }).toString()}`,
  );
  const pending =
    runs.value?.some(
      (run) => run.status === "queued" || run.status === "running",
    ) ?? false;
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => {
      runs.reload();
      setRevision((value) => value + 1);
    }, 2000);
    return () => {
      clearTimeout(timer);
    };
  }, [pending, runs]);
  function refresh() {
    setSelected([]);
    setRevision((value) => value + 1);
    runs.reload();
    onDataChanged();
  }
  async function decide(status: "accepted" | "rejected") {
    if (!selected.length || busy || isComposing()) return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const run = await decideRelations(selected, status, t("kgReviewReason"));
      if (run.status !== "SUCCEEDED")
        throw new Error(run.error || t("evActionFailed"));
      setSaved(true);
      refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  const types = [
    ...new Set(
      (schemas.value ?? []).flatMap((schema) =>
        schema.entity_types.map((item) => item.name),
      ),
    ),
  ].sort();
  return (
    <div className="kg-workspace">
      <div className="kg-toolbar">
        <label>
          {t("kgVersion")}
          <select
            aria-label={t("kgVersion")}
            value={versionId}
            onBlur={(event) => {
              setVersion(event.target.value);
              setSelected([]);
              setEntity(null);
              setRelationId("");
            }}
            onChange={(event) => {
              setVersion(event.target.value);
              setSelected([]);
              setEntity(null);
              setRelationId("");
            }}
          >
            {orderedVersions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id}
              </option>
            ))}
          </select>
        </label>
        <button className="button" onClick={refresh}>
          {t("kgRefresh")}
        </button>
      </div>
      <ResourceState {...versions} onRetry={versions.reload} />
      <ResourceState {...schemas} onRetry={schemas.reload} />
      <ResourceState {...profiles} onRetry={profiles.reload} />
      <KGExtractionForm
        key={`${datasetId}:${versionId}`}
        datasetId={datasetId}
        versionId={versionId}
        schemas={schemas.value ?? []}
        profiles={profiles.value ?? []}
        onChanged={refresh}
        onOpenReceipt={onOpenReceipt}
      />
      {pending && <p role="status">{t("kgPending")}</p>}
      <section className="card kg-results">
        <div className="kg-tabs" role="tablist" aria-label={t("kgNav")}>
          {(Object.keys(tabs) as (keyof typeof tabs)[]).map((key) => (
            <button
              type="button"
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => {
                setTab(key);
              }}
            >
              {t(tabs[key])}
            </button>
          ))}
        </div>
        {(["relations", "entities", "graph"] as string[]).includes(tab) && (
          <KGFilters
            value={filters}
            types={types}
            onChange={(next) => {
              setFilters(next);
              setSelected([]);
              setSaved(false);
            }}
          />
        )}
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        {saved && <p role="status">{t("kgReviewSaved")}</p>}
        {(tab === "relations" || tab === "entities") && (
          <>
            <ResourceState {...resource} onRetry={refresh} />
            {resource.value?.truncated && (
              <p className="warning-banner">{t("kgBounded")}</p>
            )}
          </>
        )}
        {tab === "relations" && (
          <>
            <div className="kg-selection">
              <strong>{t("kgSelected", { count: selected.length })}</strong>
              <span>
                {t("kgRelationCount", {
                  count: resource.value?.relations.length ?? 0,
                })}
              </span>
              <button
                className="button"
                disabled={!selected.length || busy || resource.loading}
                onClick={() => {
                  void decide("accepted");
                }}
              >
                {t("kgAccept")}
              </button>
              <button
                className="button danger"
                disabled={!selected.length || busy || resource.loading}
                onClick={() => {
                  void decide("rejected");
                }}
              >
                {t("kgReject")}
              </button>
            </div>
            {resource.value && (
              <KGRelations
                relations={resource.value.relations}
                selected={selected}
                onSelect={setSelected}
                onInspect={setRelationId}
              />
            )}
          </>
        )}
        {tab === "entities" && resource.value && (
          <KGEntities
            entities={resource.value.entities}
            onInspect={setEntity}
          />
        )}
        {tab === "graph" && (
          <KGGraphPanel
            query={query}
            revision={revision}
            onInspect={setRelationId}
          />
        )}
        {(tab === "runs" || tab === "proposals") && (
          <>
            <ResourceState {...runs} onRetry={runs.reload} />
            <KGReports
              runs={runs.value ?? []}
              proposalsOnly={tab === "proposals"}
            />
          </>
        )}
        {tab === "evaluations" && <KGEvaluations />}
      </section>
      {relationId && (
        <KGRelationDrawer
          key={relationId}
          assertionId={relationId}
          onClose={() => {
            setRelationId("");
          }}
        />
      )}
      {entity && (
        <KGEntityDrawer
          key={entity.asset_ref.asset_id}
          entity={entity}
          versionId={versionId}
          onClose={() => {
            setEntity(null);
          }}
        />
      )}
    </div>
  );
}
