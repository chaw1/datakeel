import { useState } from "react";

import { get } from "../../api/client";
import { useI18n } from "../../i18n/useI18n";

import { executeProduction, prepareProduction } from "./actions";

import type { ActionPlan } from "../../api/types";

/** What finalization would do, in counts a project manager can check at a glance. */
export interface FinalizationSummary {
  tasks: number;
  blocked: number;
  datasetId: string;
  versionId: string;
}

export function FinalizationPanel({
  projectId,
  ready,
  summary,
  onChanged,
}: {
  projectId: string;
  ready: boolean;
  summary?: FinalizationSummary;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [dataset, setDataset] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function prepare() {
    if (!ready || busy) return;
    setBusy(true);
    setError("");
    try {
      setPlan(
        await prepareProduction("finalize_project", { project_id: projectId }),
      );
      if (summary)
        setDataset(
          await get<{ name: string }>(
            `/api/datasets/${encodeURIComponent(summary.datasetId)}`,
          ).then(
            (value) => value.name,
            () => summary.datasetId,
          ),
        );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("wbError"));
    } finally {
      setBusy(false);
    }
  }
  async function finalize() {
    if (!plan || busy || !ready) return;
    setBusy(true);
    setError("");
    try {
      await executeProduction(plan, true);
      setPlan(null);
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("wbError"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label={t("wbFinalization")}>
      <button
        type="button"
        className="button primary"
        disabled={!ready || busy}
        onClick={() => {
          void prepare();
        }}
      >
        {t("wbFinalize")}
      </button>
      {summary && summary.blocked > 0 && !plan && (
        <p className="muted">
          {t("wbFinalizeBlocked", { count: summary.blocked })}
        </p>
      )}
      {plan && (
        <div
          className="card wb-finalization"
          role="dialog"
          aria-modal="false"
          aria-label={t("wbFinalization")}
        >
          <h2>{t("wbFinalization")}</h2>
          <p>{t("wbFinalizeDescription")}</p>
          {summary ? (
            <ul className="wb-plan-summary">
              <li>{t("wbFinalizeTasks", { count: summary.tasks })}</li>
              <li>
                {t("wbFinalizeTarget", {
                  dataset: dataset || summary.datasetId,
                  version: summary.versionId.slice(0, 8),
                })}
              </li>
              <li>
                {summary.blocked
                  ? t("wbFinalizeBlocked", { count: summary.blocked })
                  : t("wbFinalizeNothingBlocked")}
              </li>
            </ul>
          ) : (
            <p>{t("wbPlanObjects", { count: plan.impact.object_count })}</p>
          )}
          <details className="wb-plan-details">
            <summary>{t("wbPlanRaw")}</summary>
            <dl>
              <dt>{t("wbPlanDigest")}</dt>
              <dd>
                <code>{plan.plan_digest}</code>
              </dd>
            </dl>
            <pre>{JSON.stringify(plan.canonical_params, null, 2)}</pre>
          </details>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setPlan(null);
            }}
          >
            {t("wbCancel")}
          </button>
          <button
            type="button"
            className="button primary"
            disabled={!ready || busy}
            onClick={() => {
              void finalize();
            }}
          >
            {t("wbSignFinalize")}
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </section>
  );
}
