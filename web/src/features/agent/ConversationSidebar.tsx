import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import { BudgetFields } from "./BudgetFields";

import type {
  Conversation,
  ConversationCreate,
  Dataset,
} from "../../api/types";

export function ConversationSidebar({
  conversations,
  datasets,
  selectedId,
  datasetId,
  creating,
  disabled,
  onSelect,
  onCreate,
}: {
  conversations: Conversation[];
  datasets: Dataset[];
  selectedId: string;
  datasetId: string;
  creating: boolean;
  disabled: boolean;
  onSelect: (id: string) => void;
  onCreate: (
    datasetId: string,
    dryRun: boolean,
    budget: ConversationCreate["budget"],
  ) => void;
}) {
  const { t, locale } = useI18n();
  const isComposing = useCompositionGuard();
  const [scope, setScope] = useState<string | null>(null);
  const [dryRun, setDryRun] = useState(false);
  const [budget, setBudget] = useState<
    NonNullable<ConversationCreate["budget"]>
  >({
    conversation_tokens: 100000,
    daily_tokens: 1000000,
    conversation_usd: "1",
    daily_usd: "10",
  });
  return (
    <aside className="card conversation-sidebar">
      <h2>{t("conversations")}</h2>
      <label htmlFor="conversation-dataset">{t("conversationDataset")}</label>
      <select
        id="conversation-dataset"
        value={scope ?? datasetId}
        disabled={disabled || creating}
        onChange={(event) => {
          setScope(event.target.value);
        }}
        onBlur={(event) => {
          setScope(event.target.value);
        }}
      >
        <option value="">{t("noDatasetScope")}</option>
        {datasets.map((dataset) => (
          <option key={dataset.id} value={dataset.id}>
            {dataset.name}
          </option>
        ))}
      </select>
      <label className="dry-run-toggle">
        <input
          type="checkbox"
          checked={dryRun}
          disabled={disabled || creating}
          onChange={(event) => {
            setDryRun(event.target.checked);
          }}
        />
        {t("dryRun")}
      </label>
      <p className="muted small">{t("dryRunExplanation")}</p>
      <BudgetFields
        value={budget}
        onChange={setBudget}
        disabled={disabled || creating}
      />
      <button
        className="button"
        disabled={disabled || creating}
        onKeyDown={(event) => {
          if (isComposing(event.nativeEvent)) event.preventDefault();
        }}
        onClick={() => {
          if (!isComposing()) onCreate(scope ?? datasetId, dryRun, budget);
        }}
      >
        {t(creating ? "agentWorking" : "newConversation")}
      </button>
      <nav aria-label={t("conversations")} className="conversation-list">
        {conversations.map((conversation) => (
          <button
            key={conversation.id}
            className={conversation.id === selectedId ? "active" : ""}
            aria-current={conversation.id === selectedId ? "page" : undefined}
            disabled={disabled}
            onKeyDown={(event) => {
              if (isComposing(event.nativeEvent)) event.preventDefault();
            }}
            onClick={() => {
              if (!isComposing()) onSelect(conversation.id);
            }}
          >
            <span>
              {conversation.messages
                .find((message) => message.role === "user")
                ?.content.slice(0, 70) ||
                t("conversationLabel", { id: conversation.id.slice(0, 8) })}
            </span>
            <small>{date(conversation.created_at, locale)}</small>
          </button>
        ))}
      </nav>
      {!conversations.length && (
        <p className="muted small">{t("noConversations")}</p>
      )}
    </aside>
  );
}
