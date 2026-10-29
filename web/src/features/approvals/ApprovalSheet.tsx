import { useState } from "react";

import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";
import { bytes, date } from "../../lib/format";
import { useClock } from "../../lib/useClock";
import { ActionReceipt } from "../actions/ActionReceipt";
import { CustomCodeApproval } from "../custom-operators/CustomCodeApproval";
import { KGApprovalEstimate } from "../kg/KGApprovalEstimate";

import { approvalActions } from "./approvalActions";
import { ApprovalObjects } from "./ApprovalObjects";
import { isMetricPlan } from "./metricObject";
import { useApproval } from "./useApproval";

import type { ApprovalProps } from "./useApproval";

import "./approval.css";

// Releases and selected versions may carry an explicit, server-capped budget.
const BUDGET_ACTIONS = new Set([
  "publish_release",
  "create_version_from_selection",
]);

export function ApprovalSheet(props: ApprovalProps) {
  const { plan, onOpenReceipt, readOnly = false } = props;
  const { t, locale } = useI18n();
  const approval = useApproval(props);
  const now = useClock();
  const seconds = Math.max(
    0,
    Math.ceil((new Date(plan.expires_at).getTime() - now) / 1000),
  );
  const expired = seconds === 0;
  const [copy, setCopy] = useState<"ready" | "copied" | "error">("ready");
  const action = t(approvalActions[plan.action_type]);
  async function copyDigest() {
    try {
      await navigator.clipboard.writeText(plan.plan_digest);
      setCopy("copied");
    } catch {
      setCopy("error");
    }
  }
  return (
    <article
      className="plan-card approval-sheet"
      aria-label={`${t("actionPlan")}: ${plan.action_type}`}
      data-plan-id={plan.id}
    >
      <header className="approval-heading">
        <div>
          <p className="approval-kicker">
            {t("approvalSheet")} · {t(approval.status)}
          </p>
          <h3>{action}</h3>
        </div>
        <div className="approval-serial">
          <span>{t("approvalPlanNumber")}</span>
          <code title={plan.id}>{plan.id.slice(0, 8)}</code>
        </div>
      </header>
      <dl className="approval-fields">
        <div>
          <dt>{t("approvalAction")}</dt>
          <dd>
            <code>{plan.action_type}</code>
          </dd>
        </div>
        <div>
          <dt>{t("approvalSource")}</dt>
          <dd>
            {plan.session_id ? (
              <a
                href={
                  plan.agent_id === "datakeel-workflow"
                    ? `#/workflows?${new URLSearchParams({ run: plan.session_id }).toString()}`
                    : `#/agent?${new URLSearchParams({ conversation: plan.session_id }).toString()}`
                }
              >
                {t(
                  plan.agent_id === "datakeel-workflow"
                    ? "workflowSource"
                    : "approvalSourceConversation",
                  {
                    id: plan.session_id.slice(0, 8),
                  },
                )}
              </a>
            ) : (
              t("approvalLocalSource")
            )}
          </dd>
        </div>
        <div>
          <dt>{t("approvalImpact")}</dt>
          <dd>
            {t(
              isMetricPlan(plan)
                ? "approvalMetricImpactSummary"
                : "approvalImpactSummary",
              {
                count: plan.impact.object_count,
                size: bytes(plan.impact.total_bytes),
              },
            )}
          </dd>
        </div>
        {BUDGET_ACTIONS.has(plan.action_type) && (
          <div>
            <dt>{t("approvalBudget")}</dt>
            <dd>
              {t("approvalBudgetSummary", {
                count: plan.context.max_objects,
                size: bytes(plan.context.max_bytes),
              })}
            </dd>
          </div>
        )}
        <div>
          <dt>{t("externalTransfer")}</dt>
          <dd>
            {t(plan.external ? "approvalTransfer" : "approvalNoTransfer", {
              size: bytes(plan.impact.total_bytes),
            })}
          </dd>
        </div>
        <div>
          <dt>{t("reversibility")}</dt>
          <dd>
            <span
              className={
                plan.reversible
                  ? "approval-reversible"
                  : "approval-irreversible"
              }
            >
              {t(plan.reversible ? "reversibleAction" : "irreversibleAction")}
            </span>
            {!plan.reversible && <span>{t("approvalCannotUndo")}</span>}
          </dd>
        </div>
        <div>
          <dt>{t("approvalRequired")}</dt>
          <dd>{t(approval.requiresApproval ? "yes" : "no")}</dd>
        </div>
        <div>
          <dt>{t("planDigest")}</dt>
          <dd className="approval-digest">
            <code title={plan.plan_digest}>{plan.plan_digest}</code>
            <button
              type="button"
              className="text-button"
              onClick={() => {
                void copyDigest();
              }}
            >
              {t(copy === "copied" ? "approvalCopied" : "approvalCopyDigest")}
            </button>
          </dd>
        </div>
        <div>
          <dt>{t("approvalValidity")}</dt>
          <dd>
            <time dateTime={plan.expires_at}>
              {date(plan.expires_at, locale)}
            </time>
            <span
              className={expired ? "approval-expired" : "approval-countdown"}
              data-expired={expired}
            >
              {t(expired ? "approvalExpired" : "approvalRemaining", {
                minutes: Math.floor(seconds / 60),
                seconds: seconds % 60,
              })}
            </span>
          </dd>
        </div>
      </dl>
      <CustomCodeApproval plan={plan} />
      <KGApprovalEstimate plan={plan} />
      <ApprovalObjects plan={plan} />
      <p className="approval-footnote">
        {t("approvalFrozenAt", { date: date(plan.created_at, locale) })}
      </p>
      <details className="approval-parameters">
        <summary>{t("planParameters")}</summary>
        <pre>{JSON.stringify(plan.canonical_params, null, 2)}</pre>
      </details>
      {copy === "error" && (
        <p role="status" className="muted">
          {t("approvalCopyFailed")}
        </p>
      )}
      {approval.error && (
        <p className="error-text" role="alert">
          {approval.error}
        </p>
      )}
      {expired && !approval.terminal && (
        <p className="muted" role="status">
          {t("planExpired")}
        </p>
      )}
      {approval.rejected && (
        <p className="muted" role="status">
          {t("planRejected")}
        </p>
      )}
      <div className="approval-signature">
        <div className="approval-signer">
          <span>{t("approvalSigner")}</span>
          <span className="approval-signature-line">
            {approval.requiresApproval ? "local" : "—"}
          </span>
        </div>
        {!readOnly && !approval.terminal && (
          <div className="approval-controls">
            {approval.requiresApproval && (
              <button
                className="button subtle"
                type="button"
                disabled={approval.busy || expired}
                onKeyDown={(event) => {
                  if (approval.isComposing(event.nativeEvent))
                    event.preventDefault();
                }}
                onClick={() => {
                  void approval.decide(false);
                }}
              >
                {t("approvalReturn")}
              </button>
            )}
            <button
              className={`button ${!plan.reversible ? "approval-destructive" : "primary"}`}
              type="button"
              disabled={approval.busy || expired}
              onKeyDown={(event) => {
                if (approval.isComposing(event.nativeEvent))
                  event.preventDefault();
              }}
              onClick={() => {
                void approval.decide(true);
              }}
            >
              <Icon name="check" size={16} />
              {t(
                approval.busy
                  ? "planWorking"
                  : approval.requiresApproval
                    ? "approvalSignAction"
                    : "executeAction",
                { action },
              )}
            </button>
          </div>
        )}
      </div>
      <p className="approval-frozen-notice">{t("approvalFrozenNotice")}</p>
      {approval.run && (
        <ActionReceipt run={approval.run} onOpenReceipt={onOpenReceipt} />
      )}
    </article>
  );
}
