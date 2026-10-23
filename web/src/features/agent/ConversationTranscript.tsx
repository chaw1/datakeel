import { useEffect, useRef } from "react";

import { useI18n } from "../../i18n/useI18n";

import { AgentObservation } from "./AgentObservation";

import type { AgentEvent, Conversation } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function ConversationTranscript({
  conversation,
  live,
  busy,
  onResolved,
  onOpenReceipt,
}: {
  conversation: Conversation;
  live: { content: string; events: AgentEvent[] };
  busy: boolean;
  onResolved: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (panel.current) panel.current.scrollTop = panel.current.scrollHeight;
  }, [conversation.events.length, live.events.length, live.content]);
  const users = conversation.messages
    .filter((message) => message.role === "user")
    .map((message) => message.content);
  if (live.content) users.push(live.content);
  const groups: AgentEvent[][] = [[]];
  for (const event of [...conversation.events, ...live.events]) {
    groups[groups.length - 1].push(event);
    if (event.event === "done") groups.push([]);
  }
  const receipts = new Set<string>();
  return (
    <div
      ref={panel}
      className="conversation-transcript"
      role="region"
      aria-label={t("conversationActivity")}
    >
      {!users.length && (
        <div className="empty-state">
          <p>{t("conversationEmpty")}</p>
        </div>
      )}
      {groups.map((events, index) => (
        <section
          className="conversation-turn"
          key={events[0]?.id ?? `turn-${String(index)}`}
        >
          {users[index] && (
            <div className="user-message">
              <span className="eyebrow">{t("userMessage")}</span>
              <p>{users[index]}</p>
            </div>
          )}
          {events.map((event) => {
            const runId = ["plan", "receipt"].includes(event.event)
              ? event.outcome?.run?.id
              : undefined;
            const receiptVisible = !runId || !receipts.has(runId);
            if (runId) receipts.add(runId);
            return (
              <AgentObservation
                receiptVisible={receiptVisible}
                key={event.id}
                event={event}
                dryRun={conversation.config.dry_run}
                busy={busy}
                onResolved={onResolved}
                onOpenReceipt={onOpenReceipt}
              />
            );
          })}
        </section>
      ))}
      {busy && (
        <p role="status" className="agent-streaming">
          {t("streamText")}
        </p>
      )}
    </div>
  );
}
