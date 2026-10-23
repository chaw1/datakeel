import { useState } from "react";

import { decidePlan } from "../../api/actions";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { PlanCard } from "../actions/PlanCard";

import type { ActionPlan, ActionRun } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function ApprovalList({
  plans,
  onResolved,
  onOpenReceipt,
}: {
  plans: ActionPlan[];
  onResolved: (run: ActionRun | null) => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const selectedPlans = plans.filter((plan) => selected.includes(plan.id));
  async function rejectSelected() {
    if (busy || !selectedPlans.length || isComposing()) return;
    setBusy(true);
    setMessage("");
    setErrors([]);
    const rejected: string[] = [];
    const failures: string[] = [];
    for (const plan of selectedPlans) {
      try {
        await decidePlan(plan, false);
        rejected.push(plan.id);
      } catch (reason) {
        failures.push(
          `${plan.action_type}: ${reason instanceof Error ? reason.message : t("approveFailure")}`,
        );
      }
    }
    setSelected((current) => current.filter((id) => !rejected.includes(id)));
    setMessage(t("rejectedPlans", { count: rejected.length }));
    setErrors(failures);
    setBusy(false);
    if (rejected.length) onResolved(null);
  }
  return (
    <>
      <div className="section-heading">
        <h2>
          {t("pendingApprovals")}{" "}
          <span className="count-pill">{plans.length}</span>
        </h2>
        <div className="selection-actions">
          <span>{t("approvalSelection", { count: selectedPlans.length })}</span>
          <button
            className="button subtle"
            disabled={busy || !selectedPlans.length}
            onKeyDown={(event) => {
              if (isComposing(event.nativeEvent)) event.preventDefault();
            }}
            onClick={() => {
              void rejectSelected();
            }}
          >
            {t(busy ? "planWorking" : "rejectSelected")}
          </button>
        </div>
      </div>
      {message && (
        <p role="status" className="muted">
          {message}
        </p>
      )}
      {errors.length > 0 && (
        <div role="alert" className="error-banner">
          <div>
            <strong>{t("batchRejectFailed")}</strong>
            {errors.map((error) => (
              <p key={error}>{error}</p>
            ))}
          </div>
        </div>
      )}
      {!plans.length && (
        <div className="card empty-state">
          <p>{t("noPendingApprovals")}</p>
        </div>
      )}
      <div className="approval-grid">
        {plans.map((plan) => (
          <div className="approval-item" key={plan.id}>
            <label className="plan-select">
              <input
                type="checkbox"
                disabled={busy}
                checked={selected.includes(plan.id)}
                onChange={(event) => {
                  setSelected((current) =>
                    event.target.checked
                      ? [...current, plan.id]
                      : current.filter((id) => id !== plan.id),
                  );
                }}
              />
              {t("selectPlan", { action: plan.action_type })}
            </label>
            <PlanCard
              plan={plan}
              readOnly={busy}
              onResolved={onResolved}
              onOpenReceipt={onOpenReceipt}
            />
          </div>
        ))}
      </div>
    </>
  );
}
