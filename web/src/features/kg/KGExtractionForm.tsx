import { useState } from "react";

import { post } from "../../api/client";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { ActionReceipt } from "../actions/ActionReceipt";
import { PlanCard } from "../actions/PlanCard";

import type { KGProfile, KGSchema } from "../../api/kg";
import type { ActionPlan, ActionRun } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function KGExtractionForm({
  datasetId,
  versionId,
  schemas,
  profiles,
  onChanged,
  onOpenReceipt,
}: {
  datasetId: string;
  versionId: string;
  schemas: KGSchema[];
  profiles: KGProfile[];
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [schema, setSchema] = useState("");
  const [profile, setProfile] = useState("");
  const [budget, setBudget] = useState("");
  const [cost, setCost] = useState("");
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [run, setRun] = useState<ActionRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const activeSchema = schema || schemas[0]?.id || "";
  const activeProfile =
    profile ||
    profiles.find((item) => item.id === "replay-demo")?.id ||
    profiles[0]?.id ||
    "";
  async function prepare() {
    if (busy || !versionId || !activeSchema || !activeProfile || isComposing())
      return;
    setBusy(true);
    setError("");
    setRun(null);
    try {
      setPlan(
        await post<ActionPlan>("/api/actions/run_kg_extraction/prepare", {
          dataset_id: datasetId,
          version_id: versionId,
          schema_id: activeSchema,
          profile_id: activeProfile,
          ...(budget ? { budget_tokens: Number(budget) } : {}),
          ...(cost ? { max_cost_usd: cost } : {}),
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="kg-extraction">
      <summary>{t("kgPrepare")}</summary>
      <p>{t("kgExtractHint")}</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void prepare();
        }}
      >
        <div className="kg-filters">
          <label>
            {t("kgSchema")}
            <select
              aria-label={t("kgSchema")}
              disabled={!!plan || busy}
              value={activeSchema}
              onBlur={(event) => {
                setSchema(event.target.value);
              }}
              onChange={(event) => {
                setSchema(event.target.value);
              }}
            >
              {schemas.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id} · {item.version}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("kgProfile")}
            <select
              aria-label={t("kgProfile")}
              disabled={!!plan || busy}
              value={activeProfile}
              onBlur={(event) => {
                setProfile(event.target.value);
              }}
              onChange={(event) => {
                setProfile(event.target.value);
              }}
            >
              {profiles.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id} · {item.model}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("kgBudget")}
            <input
              type="number"
              min="1"
              step="1"
              disabled={!!plan || busy}
              value={budget}
              onChange={(event) => {
                setBudget(event.target.value);
              }}
            />
          </label>
          <label>
            {t("kgCostBudget")}
            <input
              type="number"
              min="0"
              step="0.000001"
              disabled={!!plan || busy}
              value={cost}
              onChange={(event) => {
                setCost(event.target.value);
              }}
            />
          </label>
        </div>
        <button
          className="button primary"
          type="submit"
          disabled={
            !!plan || busy || !versionId || !activeSchema || !activeProfile
          }
        >
          {t(busy ? "kgPreparing" : "kgPrepare")}
        </button>
      </form>
      {!versionId && <p>{t("kgMissingVersion")}</p>}
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {plan && (
        <PlanCard
          plan={plan}
          onOpenReceipt={onOpenReceipt}
          onResolved={(outcome) => {
            setRun(outcome);
            setPlan(null);
            onChanged();
          }}
          onInvalidated={() => {
            setPlan(null);
          }}
        />
      )}
      {run && <ActionReceipt run={run} onOpenReceipt={onOpenReceipt} />}
    </details>
  );
}
