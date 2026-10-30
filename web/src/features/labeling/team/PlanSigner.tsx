import { useI18n } from "../../../i18n/useI18n";

import type { ActionPlan } from "../../../api/types";
import type { ReactNode } from "react";

/**
 * A prepared plan, said in plain words first; the digest and raw parameters stay under
 * "Details". Nothing runs until a person presses the sign button here.
 */
export function PlanSigner({
  title,
  plan,
  children,
  signLabel,
  busy,
  onSign,
  onCancel,
}: {
  title: string;
  plan: ActionPlan;
  children: ReactNode;
  signLabel: string;
  busy: boolean;
  onSign: () => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  return (
    <div
      className="card wb-plan"
      role="dialog"
      aria-modal="false"
      aria-label={title}
    >
      <h3>{title}</h3>
      {children}
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
      <div className="wb-plan-actions">
        <button type="button" disabled={busy} onClick={onCancel}>
          {t("wbCancel")}
        </button>
        <button
          type="button"
          className="button primary"
          disabled={busy}
          onClick={onSign}
        >
          {signLabel}
        </button>
      </div>
    </div>
  );
}

/** Reversible plans run directly; the rest need the separate approval record first. */
export function needsApproval(plan: ActionPlan) {
  return !plan.reversible || plan.external;
}
