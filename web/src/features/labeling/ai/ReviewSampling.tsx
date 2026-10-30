import { useState } from "react";

import { useI18n } from "../../../i18n/useI18n";
import { actionMessage } from "../actionErrors";
import { executeProduction, prepareProduction } from "../actions";
import { needsApproval, PlanSigner } from "../team/PlanSigner";

import { ratio } from "./format";
import "./ai.css";

import type { ProjectWorkbench } from "../../../api/production";
import type { ActionPlan } from "../../../api/types";

/**
 * The share of low-risk submissions a person still reviews. Raising it runs at once;
 * lowering it is a signed plan because exempt submissions skip human review.
 */
export function ReviewSampling({
  data,
  onChanged,
}: {
  data: ProjectWorkbench;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const current = data.project.review_sample_rate;
  const [value, setValue] = useState(
    String(Number((current * 100).toFixed(1))),
  );
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rate = Number(value) / 100;
  const valid =
    value.trim() !== "" && Number.isFinite(rate) && rate > 0 && rate <= 1;
  async function run(step: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await step();
    } catch (reason) {
      setPlan(null);
      setError(actionMessage(reason, t, t("wbError")));
    } finally {
      setBusy(false);
    }
  }
  async function execute(prepared: ActionPlan) {
    await executeProduction(prepared, needsApproval(prepared));
    setPlan(null);
    onChanged();
  }
  return (
    <section
      className="card wb-review-sampling"
      aria-label={t("wbReviewSampling")}
    >
      <h2>{t("wbReviewSampling")}</h2>
      <p>{t("wbReviewSamplingCurrent", { rate: ratio(current) })}</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          void run(async () => {
            const prepared = await prepareProduction("configure_project", {
              project_id: data.project.id,
              review_sample_rate: rate,
            });
            if (needsApproval(prepared)) setPlan(prepared);
            else await execute(prepared);
          });
        }}
      >
        <fieldset className="wb-sampling-fields" disabled={busy || !!plan}>
          <label>
            {t("wbReviewSamplingInput")}
            <input
              type="number"
              min={0.1}
              max={100}
              step="any"
              value={value}
              onChange={(event) => {
                setValue(event.target.value);
              }}
            />
          </label>
          <button
            type="submit"
            className="button primary"
            disabled={!valid || rate === current}
          >
            {t("wbReviewSamplingPrepare")}
          </button>
        </fieldset>
      </form>
      {plan && (
        <PlanSigner
          title={t("wbReviewSamplingPlan")}
          plan={plan}
          busy={busy}
          signLabel={t("wbSignReviewSampling")}
          onCancel={() => {
            setPlan(null);
          }}
          onSign={() => {
            void run(() => execute(plan));
          }}
        >
          <p>
            {t("wbReviewSamplingChange", {
              from: ratio(current),
              to: ratio(rate),
            })}
          </p>
          <p>{t("wbReviewSamplingPlanText")}</p>
        </PlanSigner>
      )}
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </section>
  );
}
