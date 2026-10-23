import { useI18n } from "../../i18n/useI18n";
import { ActionReceipt } from "../actions/ActionReceipt";
import { PlanCard } from "../actions/PlanCard";

import { AgentRouting } from "./AgentRouting";

import type { AgentEvent } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";
import type { MessageKey } from "../../i18n/en";

const reasons: Partial<Record<string, MessageKey>> = {
  budget_exceeded: "budgetStopped",
  repeated_call: "repeatStopped",
  no_progress: "progressStopped",
  ping_pong: "pingPongStopped",
  tool_failures: "failureStopped",
  max_turns: "turnsStopped",
  approval_required: "waitingApproval",
  dry_run: "dryRunPlansOnly",
};
export function AgentObservation({
  event,
  dryRun,
  busy,
  onResolved,
  onOpenReceipt,
  receiptVisible = true,
}: {
  receiptVisible?: boolean;
  event: AgentEvent;
  dryRun: boolean;
  busy: boolean;
  onResolved: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const reasonKey = event.stop_reason ? reasons[event.stop_reason] : undefined;
  if (
    event.event === "route" ||
    (event.event === "done" && !!event.model_routes?.length)
  )
    return <AgentRouting event={event} />;
  if (event.event === "text" && event.text)
    return (
      <div className="assistant-text">
        <span className="eyebrow">{t("assistantMessage")}</span>
        <p>{event.text}</p>
      </div>
    );
  if (event.event === "tool_call" && event.call)
    return (
      <details className="tool-observation">
        <summary>
          {t("toolCall")} · <code>{event.call.name}</code>
        </summary>
        <h4>{t("toolArguments")}</h4>
        <pre>{JSON.stringify(event.call.arguments, null, 2)}</pre>
      </details>
    );
  if (event.event === "tool_result" && event.outcome)
    return (
      <details className="tool-observation">
        <summary>
          {t("toolResult")} · <code>{event.outcome.name}</code>
          <span className="badge gray">{t(event.outcome.status)}</span>
        </summary>
        {event.outcome.error && (
          <p className="error-text">{event.outcome.error}</p>
        )}
        <pre>{JSON.stringify(event.outcome.content, null, 2)}</pre>
      </details>
    );
  if (event.event === "plan" && event.outcome?.plan)
    return (
      <div className="conversation-plan">
        <PlanCard
          key={`${event.outcome.plan.id}:${event.outcome.plan.status}`}
          plan={event.outcome.plan}
          readOnly={dryRun || busy}
          onResolved={onResolved}
          onInvalidated={onResolved}
          onOpenReceipt={onOpenReceipt}
        />
        {dryRun && <p className="muted small">{t("dryRunPlansOnly")}</p>}
        {receiptVisible && event.outcome.run && (
          <ActionReceipt
            run={event.outcome.run}
            onOpenReceipt={onOpenReceipt}
          />
        )}
      </div>
    );
  if (receiptVisible && event.event === "receipt" && event.outcome?.run)
    return (
      <ActionReceipt run={event.outcome.run} onOpenReceipt={onOpenReceipt} />
    );
  if (event.event === "stopped")
    return (
      <div className="agent-stop" role="status">
        <strong>{t("agentStopped")}</strong>
        <p>{reasonKey ? t(reasonKey) : event.stop_reason}</p>
        {event.text && !reasonKey && <p>{event.text}</p>}
      </div>
    );
  return null;
}
