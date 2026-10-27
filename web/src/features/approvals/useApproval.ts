import { useRef, useState } from "react";

import { decidePlan, executePlan } from "../../api/actions";
import { ApiError } from "../../api/client";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import type { ActionPlan, ActionRun } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export type ApprovalProps = {
  plan: ActionPlan;
  onResolved?: (run: ActionRun | null) => void;
  onInvalidated?: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
  readOnly?: boolean;
};

export function useApproval({
  plan,
  onResolved,
  onInvalidated,
  readOnly,
}: ApprovalProps) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [rejected, setRejected] = useState(false);
  const [authorized, setAuthorized] = useState(plan.status === "APPROVED");
  const [run, setRun] = useState<ActionRun | null>(null);
  const requiresApproval =
    !plan.reversible ||
    plan.external ||
    plan.action_type === "confirm_metric_draft";
  const terminal =
    rejected || run !== null || !["PREPARED", "APPROVED"].includes(plan.status);
  const status = rejected
    ? "REJECTED"
    : run
      ? run.status === "FAILED" || run.status === "DENIED"
        ? run.status
        : "EXECUTED"
      : authorized
        ? "APPROVED"
        : plan.status;
  async function decide(approve: boolean) {
    if (
      pending.current ||
      readOnly ||
      terminal ||
      isComposing() ||
      new Date(plan.expires_at).getTime() <= Date.now()
    )
      return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      if (!approve) {
        await decidePlan(plan, false);
        setRejected(true);
        onResolved?.(null);
        return;
      }
      if (requiresApproval && !authorized) {
        await decidePlan(plan, true);
        setAuthorized(true);
      }
      const result = await executePlan(plan);
      setRun(result);
      onResolved?.(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("approveFailure"));
      if (reason instanceof ApiError && [409, 410].includes(reason.status))
        onInvalidated?.();
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return {
    busy,
    error,
    rejected,
    run,
    status,
    terminal,
    requiresApproval,
    isComposing,
    decide,
  };
}
