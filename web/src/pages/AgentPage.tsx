import { useState } from "react";

import { createConversation } from "../api/agent";
import { Icon } from "../components/Icon";
import { ResourceState } from "../components/ResourceState";
import { ConversationSidebar } from "../features/agent/ConversationSidebar";
import { ConversationTranscript } from "../features/agent/ConversationTranscript";
import { MessageComposer } from "../features/agent/MessageComposer";
import { useConversation } from "../features/agent/useConversation";
import { money } from "../features/traces/format";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { Conversation, ConversationCreate, Dataset } from "../api/types";
import type { LineageTarget } from "../app/navigation";

export function AgentPage({
  datasets,
  datasetId,
  conversationId,
  onConversation,
  onOpenReceipt,
  onDataChanged,
  onTrace,
}: {
  datasets: Dataset[];
  datasetId: string;
  conversationId: string;
  onConversation: (id: string) => void;
  onOpenReceipt: (target: LineageTarget) => void;
  onDataChanged: () => void;
  onTrace: (id: string) => void;
}) {
  const { t, locale } = useI18n();
  const params = new URLSearchParams(window.location.hash.split("?")[1]);
  const [chosenConversation, setChosenConversation] = useState(
    params.get("conversation") ?? "",
  );
  const initialContent = params.get("prompt") ?? "";
  const conversations = useResource<Conversation[]>("/api/agent/conversations");
  const id =
    chosenConversation || conversationId || conversations.value?.[0]?.id || "";
  const session = useConversation(id);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  async function create(
    dataset: string,
    dryRun: boolean,
    budget: ConversationCreate["budget"],
  ) {
    setCreating(true);
    setError("");
    try {
      const value = await createConversation(dataset, dryRun, budget);
      setChosenConversation(value.id);
      onConversation(value.id);
      conversations.reload();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : t("createConversationError"),
      );
    } finally {
      setCreating(false);
    }
  }
  function refresh() {
    session.reload();
    conversations.reload();
  }
  function resolved() {
    refresh();
    onDataChanged();
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>
            {t("pageCount", {
              name: t("agentNav"),
              count: conversations.value?.length ?? 0,
            })}
          </h1>
        </div>
        <button
          className="button"
          disabled={session.live.running}
          onClick={refresh}
        >
          <Icon name="refresh" />
          {t("refresh")}
        </button>
      </div>
      <ResourceState
        loading={conversations.loading}
        error={error || conversations.error}
        onRetry={conversations.reload}
      />
      <div className="agent-layout">
        <ConversationSidebar
          conversations={conversations.value ?? []}
          datasets={datasets}
          datasetId={params.get("dataset") ?? datasetId}
          selectedId={id}
          creating={creating}
          disabled={session.live.running}
          onSelect={(value) => {
            setChosenConversation(value);
            onConversation(value);
          }}
          onCreate={(dataset, dryRun, budget) => {
            void create(dataset, dryRun, budget);
          }}
        />
        <section className="card conversation-main">
          <ResourceState {...session} onRetry={session.reload} />
          {session.value ? (
            <>
              <div className="conversation-heading">
                <div>
                  <span className="badge gray">
                    {session.value.config.model}
                  </span>
                  <span className="badge gray">
                    {t(session.value.config.dry_run ? "dryRun" : "liveActions")}
                  </span>
                </div>
                <button
                  className="text-button"
                  disabled={session.live.running}
                  onClick={() => {
                    onTrace(id);
                  }}
                >
                  {t("viewTrace")}
                  <Icon name="arrow" size={14} />
                </button>
              </div>
              {session.value.config.budget && (
                <details className="conversation-budget">
                  <summary>{t("conversationBudget")}</summary>
                  <p>
                    {t("tokenBudget", {
                      count: session.value.config.budget.conversation_tokens,
                    })}{" "}
                    ·{" "}
                    {money(
                      session.value.config.budget.conversation_usd,
                      locale,
                    )}
                  </p>
                  <p>
                    {t("dailyBudget")}:{" "}
                    {t("tokenBudget", {
                      count: session.value.config.budget.daily_tokens,
                    })}{" "}
                    · {money(session.value.config.budget.daily_usd, locale)}
                  </p>
                </details>
              )}
              <ConversationTranscript
                conversation={session.value}
                live={session.live}
                busy={session.live.running}
                onResolved={resolved}
                onOpenReceipt={onOpenReceipt}
              />
              {session.live.error && (
                <div className="error-banner" role="alert">
                  <div>
                    <strong>{t("streamInterrupted")}</strong>
                    <p>{session.live.error}</p>
                    <button onClick={refresh}>{t("reloadConversation")}</button>
                  </div>
                </div>
              )}
            </>
          ) : (
            !session.loading && (
              <div className="empty-state">
                <p>{t("chooseConversation")}</p>
              </div>
            )
          )}
          <MessageComposer
            key={id}
            initialContent={initialContent}
            disabled={!session.value || session.loading || !!session.live.error}
            busy={session.live.running}
            onSend={(content) => {
              void session.send(content).then(() => {
                conversations.reload();
                onDataChanged();
              });
            }}
          />
        </section>
      </div>
    </>
  );
}
