import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { executeProduction, prepareProduction } from "./actions";

import type { ActionPlan } from "../../api/types";

export function FinalizationPanel({
  projectId,
  ready,
  onChanged,
}: {
  projectId: string;
  ready: boolean;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function prepare() {
    setBusy(true);
    setError("");
    try {
      setPlan(
        await prepareProduction("finalize_project", { project_id: projectId }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("wbError"));
    } finally {
      setBusy(false);
    }
  }
  async function finalize() {
    if (!plan || busy) return;
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
      {plan && (
        <div
          className="card wb-finalization"
          role="dialog"
          aria-modal="false"
          aria-label={t("wbFinalization")}
        >
          <h2>{t("wbFinalization")}</h2>
          <p>{t("wbFinalizeDescription")}</p>
          <p>{t("wbPlanObjects", { count: plan.impact.object_count })}</p>
          <dl>
            <dt>{t("wbPlanDigest")}</dt>
            <dd>
              <code>{plan.plan_digest}</code>
            </dd>
          </dl>
          <pre>{JSON.stringify(plan.canonical_params, null, 2)}</pre>
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
            disabled={busy}
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
