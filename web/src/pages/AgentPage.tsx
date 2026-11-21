import { useState } from "react";

import { createConversation } from "../api/agent";
import { Icon } from "../components/Icon";
import { ResourceState } from "../components/ResourceState";
import {
  Badge,
  Button,
  EmptyState,
  PageHeader,
  Surface,
} from "../components/ui";
import { AgentCallTree } from "../features/agent/AgentCallTree";
import { contextFromQuery } from "../features/agent/agentLink";
import { ConversationSidebar } from "../features/agent/ConversationSidebar";
import { ConversationTranscript } from "../features/agent/ConversationTranscript";
import { MessageComposer } from "../features/agent/MessageComposer";
import { useConversation } from "../features/agent/useConversation";
import { money } from "../features/traces/format";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type {
  Conversation,
  ConversationCreate,
  ConversationDefaults,
  Dataset,
  ExecutionMode,
} from "../api/types";
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
  const [query, setQuery] = useState("");
  const search = query.trim();
  const conversations = useResource<Conversation[]>(
    `/api/agent/conversations${search ? `?q=${encodeURIComponent(search)}` : ""}`,
  );
  const id =
    chosenConversation || conversationId || conversations.value?.[0]?.id || "";
  const session = useConversation(id);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [setup, setSetup] = useState<ConversationDefaults | null>(null);
  const [mode, setMode] = useState<ExecutionMode>("auto");
  async function create(
    dataset: string,
    dryRun: boolean,
    budget: ConversationCreate["budget"],
  ) {
    setCreating(true);
    setError("");
    try {
      const { conversation: value, setup: used } = await createConversation(
        dataset,
        dryRun,
        budget,
      );
      setSetup(used.problem ? used : null);
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
  // The planner reads what the person is looking at: everything the entry link carried
  // (project, task, package, selected rows), the conversation's dataset first, then the
  // dataset the workspace has open.
  const pageContext = {
    ...contextFromQuery(params),
    dataset_id:
      session.value?.config.dataset_id ??
      params.get("dataset") ??
      (datasetId || null),
  };
  function say(content: string, executionMode = mode) {
    void session.send(content, pageContext, executionMode).then(() => {
      conversations.reload();
      onDataChanged();
    });
  }
  return (
    <>
      <PageHeader
        title={t("pageCount", {
          name: t("agentNav"),
          count: conversations.value?.length ?? 0,
        })}
        actions={
          <Button
            icon="refresh"
            disabled={session.live.running}
            onClick={refresh}
          >
            {t("refresh")}
          </Button>
        }
      />
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
          query={query}
          onQueryChange={setQuery}
          onSelect={(value) => {
            setChosenConversation(value);
            onConversation(value);
          }}
          onCreate={(dataset, dryRun, budget) => {
            void create(dataset, dryRun, budget);
          }}
        />
        <Surface as="section" className="conversation-main">
          {setup?.problem && (
            <div className="warning-banner" role="status">
              <div>
                <strong>{t("modelSetupProblem")}</strong>
                <p>
                  {setup.problem === "no_model_key"
                    ? t("modelSetupNoKey")
                    : t("modelSetupUnrouted", {
                        endpoint: setup.endpoint ?? "",
                      })}
                </p>
              </div>
            </div>
          )}
          <ResourceState {...session} onRetry={session.reload} />
          {session.value ? (
            <>
              <div className="conversation-heading">
                <div>
                  <Badge>{session.value.config.model}</Badge>
                  <Badge>
                    {t(session.value.config.dry_run ? "dryRun" : "liveActions")}
                  </Badge>
                </div>
                <Button
                  variant="link"
                  disabled={session.live.running}
                  onClick={() => {
                    onTrace(id);
                  }}
                >
                  {t("viewTrace")}
                  <Icon name="arrow" size={14} />
                </Button>
              </div>
              <AgentCallTree
                key={id}
                conversationId={id}
                revision={session.value.events.length}
              />
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
                onReply={say}
                onResume={(planId) => {
                  void session.resume(planId).then(() => {
                    conversations.reload();
                    onDataChanged();
                  });
                }}
                onEscalateAgent={(request) => {
                  say(request, "agent");
                }}
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
            !session.loading && <EmptyState title={t("chooseConversation")} />
          )}
          <MessageComposer
            key={id}
            initialContent={initialContent}
            disabled={!session.value || session.loading || !!session.live.error}
            busy={session.live.running}
            onSend={say}
            mode={mode}
            onModeChange={setMode}
            onStop={() => {
              void session.stop();
            }}
          />
        </Surface>
      </div>
    </>
  );
}
