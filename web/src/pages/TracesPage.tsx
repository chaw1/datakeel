import { useState } from "react";

import { Icon } from "../components/Icon";
import { ResourceState } from "../components/ResourceState";
import { CostTable } from "../features/traces/CostTable";
import { TraceList } from "../features/traces/TraceList";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { Conversation, CostSummary, ModelCallTrace } from "../api/types";

export function TracesPage({
  conversationId,
  onConversation,
}: {
  conversationId: string;
  onConversation: (id: string) => void;
}) {
  const { t } = useI18n();
  const [group, setGroup] = useState<CostSummary["group_by"]>("conversation");
  const conversations = useResource<Conversation[]>("/api/agent/conversations");
  const traces = useResource<ModelCallTrace[]>(
    `/api/harness/traces${conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : ""}`,
  );
  const costs = useResource<CostSummary[]>(
    `/api/harness/costs?group_by=${group}`,
  );
  function refresh() {
    conversations.reload();
    traces.reload();
    costs.reload();
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>
            {t("pageCount", {
              name: t("tracesNav"),
              count: traces.value?.length ?? 0,
            })}
          </h1>
        </div>
        <button className="button" onClick={refresh}>
          <Icon name="refresh" />
          {t("refresh")}
        </button>
      </div>
      <section className="card cost-summary">
        <div className="card-heading">
          <h2>{t("costSummary")}</h2>
          <select
            aria-label={t("groupCostsBy")}
            value={group}
            onChange={(event) => {
              setGroup(event.target.value as CostSummary["group_by"]);
            }}
            onBlur={(event) => {
              setGroup(event.target.value as CostSummary["group_by"]);
            }}
          >
            <option value="conversation">{t("byConversation")}</option>
            <option value="day">{t("byDay")}</option>
            <option value="model">{t("byModel")}</option>
          </select>
        </div>
        <ResourceState {...costs} onRetry={costs.reload} />
        {costs.value && (
          <CostTable costs={costs.value} onConversation={onConversation} />
        )}
      </section>
      <div className="section-heading trace-heading">
        <h2>
          {t("modelCalls")}
          {traces.value && (
            <span className="count-pill">{traces.value.length}</span>
          )}
        </h2>
        <select
          aria-label={t("traceConversation")}
          value={conversationId}
          onChange={(event) => {
            onConversation(event.target.value);
          }}
          onBlur={(event) => {
            onConversation(event.target.value);
          }}
        >
          <option value="">{t("allConversations")}</option>
          {conversations.value?.map((conversation) => (
            <option value={conversation.id} key={conversation.id}>
              {conversation.messages
                .find((message) => message.role === "user")
                ?.content.slice(0, 55) || conversation.id}
            </option>
          ))}
        </select>
      </div>
      <ResourceState
        loading={false}
        error={conversations.error}
        onRetry={conversations.reload}
      />
      <ResourceState {...traces} onRetry={traces.reload} />
      {traces.value && <TraceList traces={traces.value} />}
    </>
  );
}
