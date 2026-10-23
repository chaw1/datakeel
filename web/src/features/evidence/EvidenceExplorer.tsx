import { useEffect, useState } from "react";

import { executePlan } from "../../api/actions";
import { post } from "../../api/client";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { ActionReceipt } from "../actions/ActionReceipt";
import { PlanCard } from "../actions/PlanCard";

import { EvidenceDrawer } from "./EvidenceDrawer";
import { EvidenceEmpty } from "./EvidenceEmpty";
import { EvidenceFilters } from "./EvidenceFilters";
import { EvidenceResults } from "./EvidenceResults";
import { exactSelection, initialFilters } from "./query";
import { useEvidenceQuery } from "./useEvidenceQuery";
import "./evidence-compact.css";

import type { EvidenceFilters as Filters } from "./query";
import type {
  ActionPlan,
  ActionRun,
  Dataset,
  EvidenceSample,
} from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function EvidenceExplorer({
  datasetId,
  onDataChanged,
  onOpenReceipt,
  dataset,
  onCount,
}: {
  datasetId: string;
  onDataChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
  dataset?: Dataset;
  onCount?: (count: number) => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [filters, setFilters] = useState(initialFilters);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<EvidenceSample[]>([]);
  const [detail, setDetail] = useState<EvidenceSample | null>(null);
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [run, setRun] = useState<ActionRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const resource = useEvidenceQuery(
    datasetId,
    filters,
    cursors.at(-1) ?? null,
    revision,
  );
  const result = resource.value;
  useEffect(() => {
    if (result) onCount?.(result.total);
  }, [result, onCount]);
  const selection = exactSelection(selected);
  function refresh() {
    setSelected([]);
    setRevision((value) => value + 1);
    onDataChanged();
  }
  function filter(value: Filters) {
    setFilters(value);
    setCursors([null]);
    setSelected([]);
    setError("");
  }
  async function act(
    action:
      "create_version_from_selection" | "quarantine_files" | "delete_files",
  ) {
    if (!selection || busy || isComposing()) return;
    setBusy(true);
    setError("");
    setPlan(null);
    setRun(null);
    try {
      const prepared = await post<ActionPlan>(
        `/api/actions/${action}/prepare`,
        { selection },
      );
      if (
        action === "delete_files" ||
        !prepared.reversible ||
        prepared.external
      )
        setPlan(prepared);
      else {
        const outcome = await executePlan(prepared);
        setRun(outcome);
        if (outcome.status === "SUCCEEDED") refresh();
        else setError(outcome.error || t("evActionFailed"));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="evidence-explorer">
      <EvidenceFilters value={filters} onChange={filter} />
      <section className="card evidence-results-card">
        <div className="evidence-results-heading">
          <div>
            <p role="status">
              {result
                ? t("evResultCount", { count: result.total })
                : t("evIntro")}
            </p>
          </div>
          <button
            className="button"
            onClick={() => {
              setSelected([]);
              setRevision((value) => value + 1);
            }}
          >
            {t("refreshDataset")}
          </button>
        </div>
        <div className="evidence-selection-bar">
          <strong>{t("evSelected", { count: selected.length })}</strong>
          <div>
            {(
              [
                ["create_version_from_selection", "evCreateVersion"],
                ["quarantine_files", "evQuarantine"],
                ["delete_files", "evDelete"],
              ] as const
            ).map(([action, label]) => (
              <button
                className={`button ${action === "delete_files" ? "danger" : ""}`}
                key={action}
                disabled={!selection || busy || resource.loading}
                onKeyDown={(event) => {
                  if (isComposing(event.nativeEvent)) event.preventDefault();
                }}
                onClick={() => {
                  void act(action);
                }}
              >
                {t(busy ? "evBusy" : label)}
              </button>
            ))}
          </div>
        </div>
        {selected.length > 0 && !selection && (
          <p className="error-banner" role="alert">
            {t("evSelectionScope")}
          </p>
        )}
        {resource.invalid && (
          <p className="error-banner" role="alert">
            {t("evQualityInvalid")}
          </p>
        )}
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        <ResourceState
          {...resource}
          onRetry={() => {
            setRevision((value) => value + 1);
          }}
        />
        {result && (
          <>
            {result.truncated && (
              <p role="status" className="warning-banner">
                {t("evTruncated")}
              </p>
            )}
            {result.items.length &&
            result.items.some((item) => item.assertions.length) ? (
              <EvidenceResults
                items={result.items}
                selected={selected}
                onSelect={setSelected}
                onInspect={setDetail}
                showFootnotes={!detail}
              />
            ) : (
              <EvidenceEmpty
                datasetId={datasetId}
                dataset={dataset}
                filters={filters}
                onChange={filter}
                unextracted={result.items.length > 0}
                sourceVersion={result.items[0]?.source_version}
                onDataChanged={onDataChanged}
                onComplete={refresh}
                onOpenReceipt={onOpenReceipt}
              />
            )}
            <div className="evidence-pagination">
              <button
                className="button"
                disabled={cursors.length < 2}
                onClick={() => {
                  setCursors((value) => value.slice(0, -1));
                  setSelected([]);
                }}
              >
                {t("evPrevious")}
              </button>
              <span>{t("evPage", { page: cursors.length })}</span>
              <button
                className="button"
                disabled={!result.next_cursor}
                onClick={() => {
                  setCursors((value) => [...value, result.next_cursor]);
                  setSelected([]);
                }}
              >
                {t("evNext")}
              </button>
            </div>
          </>
        )}
      </section>
      {run && <ActionReceipt run={run} onOpenReceipt={onOpenReceipt} />}
      {plan && (
        <div className="evidence-pending-plan">
          <p role="status">{t("evPendingDelete")}</p>
          <PlanCard
            key={plan.id}
            plan={plan}
            onOpenReceipt={onOpenReceipt}
            onResolved={(outcome) => {
              if (outcome?.status === "SUCCEEDED") refresh();
            }}
            onInvalidated={() => {
              setSelected([]);
            }}
          />
        </div>
      )}
      {detail && (
        <EvidenceDrawer
          key={`${detail.asset_ref.asset_id}:${detail.source_version}`}
          sample={detail}
          onClose={() => {
            setDetail(null);
          }}
          onReviewed={refresh}
          onOpenGraph={(target) => {
            setDetail(null);
            onOpenReceipt(target);
          }}
        />
      )}
    </div>
  );
}
