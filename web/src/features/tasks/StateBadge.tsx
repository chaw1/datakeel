import { useI18n } from "../../i18n/useI18n";

import type { MessageKey } from "../../i18n/en";

export function StateBadge({ state }: { state: string }) {
  const { t } = useI18n();
  const states: Record<string, MessageKey> = {
    COMPLETED: "completedState",
    SUCCEEDED: "SUCCEEDED",
    DENIED: "DENIED",
    FAILED: "failedState",
    CANCELLED: "cancelledState",
    RUNNING: "runningState",
    PENDING: "pendingState",
    QUEUED: "queuedState",
  };
  const normalized = state.toUpperCase();
  return (
    <span
      className={`badge ${["COMPLETED", "SUCCEEDED"].includes(normalized) ? "green" : ["FAILED", "CANCELLED", "DENIED"].includes(normalized) ? "red" : "amber"}`}
    >
      <span className="status-dot" />
      {normalized in states
        ? t(states[normalized])
        : state.toLowerCase().replaceAll("_", " ")}
    </span>
  );
}
