import { useEffect, useRef, useState } from "react";

import {
  deleteAskConversation,
  listAskConversations,
  openAskConversation,
} from "../../api/ask";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import type { AskConversation } from "../../api/ask";

export function AskConversations({
  actor,
  activeId,
  disabled,
  onOpen,
  onNew,
  onDeleted,
  onBusyChange,
}: {
  actor: string;
  activeId?: string;
  disabled: boolean;
  onOpen: (conversation: AskConversation) => void;
  onNew: () => void;
  onDeleted: (id: string) => void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [items, setItems] = useState<AskConversation[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mounted = useRef(true);
  const pending = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (pending.current) onBusyChange?.(false);
      pending.current = false;
    };
  }, [onBusyChange]);
  async function perform<T>(
    operation: () => Promise<T>,
    onComplete: (value: T) => void,
  ) {
    if (busy || disabled || isComposing()) return;
    setBusy(true);
    pending.current = true;
    onBusyChange?.(true);
    setError("");
    try {
      const value = await operation();
      if (mounted.current) onComplete(value);
    } catch (reason) {
      if (mounted.current)
        setError(reason instanceof Error ? reason.message : t("askError"));
    } finally {
      if (mounted.current) {
        setBusy(false);
        pending.current = false;
        onBusyChange?.(false);
      }
    }
  }
  return (
    <section className="ask-conversations" aria-label={t("askConversations")}>
      <div className="ask-chart-controls">
        <button
          className="button"
          type="button"
          disabled={busy || disabled}
          onClick={() => {
            if (!isComposing()) onNew();
          }}
        >
          {t("askNewConversation")}
        </button>
        <button
          className="button"
          type="button"
          disabled={busy || disabled}
          onClick={() => {
            void perform(() => listAskConversations(actor), setItems);
          }}
        >
          {t("askConversations")}
        </button>
        {activeId && (
          <span className="ask-muted">
            {t("askConversationActive")}: <code>{activeId.slice(0, 8)}</code>
          </span>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {items?.length === 0 && <p>{t("askNoConversations")}</p>}
      {items && (
        <ul className="ask-conversation-list">
          {items.map((item) => (
            <li key={item.id}>
              <span>
                {item.title || t("askNewConversation")} ·{" "}
                {t("askConversationTurns", { count: item.turns.length })}
              </span>
              <button
                className="button"
                type="button"
                disabled={busy || disabled}
                aria-label={`${t("askOpenConversation")}: ${item.title}`}
                onClick={() => {
                  void perform(
                    () => openAskConversation(item.id, actor),
                    onOpen,
                  );
                }}
              >
                {t("askOpenConversation")}
              </button>
              <button
                className="button"
                type="button"
                disabled={busy || disabled}
                aria-label={`${t("askDeleteConversation")}: ${item.title}`}
                onClick={() => {
                  void perform(
                    () => deleteAskConversation(item.id, actor),
                    () => {
                      setItems(
                        (previous) =>
                          previous?.filter((entry) => entry.id !== item.id) ??
                          null,
                      );
                      onDeleted(item.id);
                    },
                  );
                }}
              >
                {t("askDeleteConversation")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
