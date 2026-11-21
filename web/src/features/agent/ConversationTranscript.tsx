import { useEffect, useRef } from "react";

import { useI18n } from "../../i18n/useI18n";

import { AgentMemoryUsage } from "./AgentMemoryUsage";
import { AgentSteps } from "./AgentSteps";

import type { PageContext } from "../../api/intents";
import type { AgentEvent, Conversation } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

function runningTools(events: AgentEvent[]) {
  const pending = new Map<string, AgentEvent[]>();
  for (const event of events) {
    const path = event.agent_path || "main";
    const calls = pending.get(path) ?? [];
    if (event.event === "tool_call") pending.set(path, [...calls, event]);
    if (event.event === "tool_result")
      pending.set(
        path,
        event.call?.id
          ? calls.filter((item) => item.call?.id !== event.call?.id)
          : calls.slice(1),
      );
    if (["stopped", "done"].includes(event.event)) pending.delete(path);
  }
  return new Set([...pending.values()].flat().map((event) => event.id));
}

function approvalPause(events: AgentEvent[]) {
  const root = events.filter(
    (event) => !event.agent_path || event.agent_path === "main",
  );
  const reversed = [...root].reverse();
  const pause = reversed.find((event) => event.event === "stopped");
  const stopped = pause ? root.indexOf(pause) : -1;
  if (
    !pause?.id ||
    pause.stop_reason !== "approval_required" ||
    root
      .slice(stopped + 1)
      .some((event) => !["done", "route"].includes(event.event))
  )
    return undefined;
  const plan = root
    .slice(0, stopped)
    .reverse()
    .find((event) => event.event === "plan")?.outcome?.plan;
  return plan && ["APPROVED", "EXECUTED"].includes(plan.status)
    ? { eventId: pause.id, planId: plan.id }
    : undefined;
}

export function ConversationTranscript({
  conversation,
  live,
  busy,
  context,
  onResolved,
  onOpenReceipt,
  onReply,
  onResume,
  onEscalateAgent,
}: {
  conversation: Conversation;
  live: { content: string; events: AgentEvent[] };
  busy: boolean;
  context?: PageContext;
  onResolved: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
  onReply?: (content: string) => void;
  onResume?: (planId: string) => void;
  onEscalateAgent?: (content: string) => void;
}) {
  const { t } = useI18n();
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (panel.current) panel.current.scrollTop = panel.current.scrollHeight;
  }, [conversation.events.length, live.events, live.content]);
  const running = busy ? runningTools(live.events) : new Set<string>();
  const users = conversation.messages
    .filter((message) => message.role === "user")
    .map((message) => message.content);
  if (live.content) users.push(live.content);
  const groups: AgentEvent[][] = [[]];
  for (const event of [...conversation.events, ...live.events]) {
    const root = !event.agent_path || event.agent_path === "main";
    // A resume starts with its receipt; it does not append another user message.
    if (
      root &&
      event.event === "receipt" &&
      groups.length > 1 &&
      !groups[groups.length - 1].length
    )
      groups.pop();
    groups[groups.length - 1].push(event);
    if (event.event === "done" && root) groups.push([]);
  }
  const latest = groups.length - (groups[groups.length - 1].length ? 1 : 2);
  const resume =
    users.length > latest + 1 && !live.content
      ? undefined
      : approvalPause(live.content ? live.events : (groups[latest] ?? []));
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
          <AgentMemoryUsage
            ids={[
              ...new Set(
                events.flatMap((event) => event.used_memory_ids ?? []),
              ),
            ]}
          />
          <AgentSteps
            events={events}
            dryRun={conversation.config.dry_run}
            busy={busy}
            runningTools={running}
            context={context}
            onResolved={onResolved}
            onOpenReceipt={onOpenReceipt}
            onReply={onReply}
            onResume={onResume}
            onEscalateAgent={onEscalateAgent}
            resume={index === latest ? resume : undefined}
            visibleReceipts={
              new Set(
                events
                  .filter((event) => {
                    const runId = ["plan", "receipt"].includes(event.event)
                      ? event.outcome?.run?.id
                      : undefined;
                    if (!runId) return true;
                    if (receipts.has(runId)) return false;
                    receipts.add(runId);
                    return true;
                  })
                  .map((event) => event.id),
              )
            }
          />
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
