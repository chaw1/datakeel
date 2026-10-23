import { useEffect, useState } from "react";

import { get, post } from "../../api/client";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { useResource } from "../../lib/useResource";
import { ActionReceipt } from "../actions/ActionReceipt";
import { PlanCard } from "../actions/PlanCard";
import { objectHref } from "../object/navigation";

import {
  evidenceSource,
  extractionInput,
  pairedImportCommand,
  supportsEvidence,
} from "./extraction";
import "./extraction.css";

import type { ActionPlan, ActionRun, Version } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function EvidenceExtraction({
  datasetId,
  sourceVersion,
  onDataChanged,
  onComplete,
  onOpenReceipt,
}: {
  datasetId: string;
  sourceVersion?: string;
  onDataChanged?: () => void;
  onComplete?: () => void;
  onOpenReceipt?: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const versions = useResource<Version[]>(
    `/api/datasets/${encodeURIComponent(datasetId)}/versions`,
  );
  const source = evidenceSource(versions.value ?? [], sourceVersion);
  const supported = source && supportsEvidence(source);
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [run, setRun] = useState<ActionRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = run?.status === "QUEUED" || run?.status === "RUNNING";
  const runId = run?.id;

  useEffect(() => {
    if (!pending || !runId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const runs = await get<ActionRun[]>("/api/actions/runs");
        if (!active) return;
        const next = runs.find((item) => item.id === runId);
        if (next) {
          setRun(next);
          setError("");
          if (!["QUEUED", "RUNNING"].includes(next.status)) {
            onDataChanged?.();
            if (next.status === "SUCCEEDED") onComplete?.();
            return;
          }
        }
      } catch (reason) {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : String(reason));
      }
      timer = setTimeout(() => {
        void poll();
      }, 2000);
    }
    timer = setTimeout(() => {
      void poll();
    }, 2000);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [pending, runId, onComplete, onDataChanged]);

  async function prepare() {
    if (!source || !supported || busy || pending || isComposing()) return;
    setBusy(true);
    setError("");
    try {
      setPlan(
        await post<ActionPlan>(
          "/api/actions/run_pipeline/prepare",
          extractionInput(datasetId, source.id),
        ),
      );
      setRun(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  function openReceipt(target: LineageTarget) {
    if (onOpenReceipt) onOpenReceipt(target);
    else if (run)
      window.location.hash = objectHref({ kind: "action_run", id: run.id });
  }
  return (
    <div className="evidence-extraction">
      <ResourceState {...versions} onRetry={versions.reload} />
      {!versions.loading &&
        !versions.error &&
        (supported ? (
          <>
            <p>{t("evExtractionReady")}</p>
            <p>
              {t("evVersion")}{" "}
              <a
                className="mono"
                href={objectHref({ kind: "version", id: source.id, datasetId })}
              >
                {source.id}
              </a>
            </p>
            {!plan && !pending && (
              <button
                className="button primary"
                disabled={busy}
                onKeyDown={(event) => {
                  if (isComposing(event.nativeEvent)) event.preventDefault();
                }}
                onClick={() => {
                  void prepare();
                }}
              >
                {t(busy ? "evBusy" : "evRunExtraction")}
              </button>
            )}
          </>
        ) : (
          <>
            <p>
              {t(source ? "evExtractionUnsupported" : "evExtractionNoSource")}
            </p>
            <details>
              <summary>{t("evPairedInstructions")}</summary>
              <p>{t("evPairedLayout")}</p>
              <p>{t("evPairedEnvironment")}</p>
              <pre>
                <code>{pairedImportCommand}</code>
              </pre>
              <p>{t("evPairedNext")}</p>
            </details>
            <a className="text-button" href="#/datasets">
              {t("evAddData")}
            </a>
          </>
        ))}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {plan && (
        <PlanCard
          plan={plan}
          onOpenReceipt={openReceipt}
          onResolved={(outcome) => {
            setRun(outcome);
            setPlan(null);
            onDataChanged?.();
            if (outcome?.status === "SUCCEEDED") onComplete?.();
          }}
          onInvalidated={() => {
            setPlan(null);
          }}
        />
      )}
      {run && (
        <>
          <ActionReceipt run={run} onOpenReceipt={openReceipt} />
          <div className="evidence-extraction-links">
            {run.task_id && (
              <a
                className="text-button"
                href={`#/runs?type=pipeline&run=${encodeURIComponent(run.task_id)}`}
              >
                {t("evExtractionTask")}
              </a>
            )}
            <a
              className="text-button"
              href={objectHref({ kind: "action_run", id: run.id })}
            >
              {t("evExtractionRun")}
            </a>
          </div>
        </>
      )}
    </div>
  );
}
