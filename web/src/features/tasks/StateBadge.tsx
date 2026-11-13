import { Badge, type BadgeTone } from "../../components/ui";
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
    PAUSED: "workflowPaused",
    SKIPPED: "workflowSkipped",
    INTERRUPTED: "workflowInterrupted",
  };
  const normalized = state.toUpperCase();
  const tone: BadgeTone = ["COMPLETED", "SUCCEEDED"].includes(normalized)
    ? "ok"
    : ["FAILED", "CANCELLED", "DENIED", "INTERRUPTED"].includes(normalized)
      ? "danger"
      : "warn";
  return (
    <Badge tone={tone} dot>
      {normalized in states
        ? t(states[normalized])
        : state.toLowerCase().replaceAll("_", " ")}
    </Badge>
  );
}
