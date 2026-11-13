import { useEffect, useRef, useState } from "react";

import { createConversation } from "../../api/agent";
import { useConversation } from "../agent/useConversation";

import type { PageContext } from "../../api/intents";
import type { Conversation } from "../../api/types";

type PendingSend = {
  id: string;
  content: string;
  context?: PageContext;
};

const defaultBudget = {
  conversation_tokens: 100000,
  daily_tokens: 1000000,
  conversation_usd: "1",
  daily_usd: "10",
};

/** Manage a lazy copilot conversation that fetches nothing while closed and creates only on send. */
export function useCopilotSession({
  open,
  datasetId,
  onConversation,
}: {
  open: boolean;
  datasetId: string;
  onConversation?: (id: string) => void;
}) {
  const [conversationId, setConversationId] = useState("");
  const [seedConversation, setSeedConversation] = useState<Conversation | null>(
    null,
  );
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [contextEnabled, setContextEnabled] = useState(true);
  const pendingRef = useRef<PendingSend | null>(null);

  const session = useConversation(open ? conversationId : "");
  const sendRef = useRef(session.send);

  useEffect(() => {
    sendRef.current = session.send;
  }, [session.send]);

  useEffect(() => {
    const pending = pendingRef.current;
    if (!open || !pending || conversationId !== pending.id) return;
    pendingRef.current = null;
    void sendRef.current(pending.content, pending.context);
  }, [open, conversationId]);

  async function sendMessage(content: string, activeContext?: PageContext) {
    const trimmed = content.trim();
    if (!trimmed || creating || session.live.running) return;
    const attached = contextEnabled ? activeContext : undefined;
    setCreateError("");
    if (conversationId) {
      await session.send(trimmed, attached);
      return;
    }
    setCreating(true);
    try {
      const created = await createConversation(datasetId, false, defaultBudget);
      pendingRef.current = {
        id: created.conversation.id,
        content: trimmed,
        context: attached,
      };
      setSeedConversation(created.conversation);
      setConversationId(created.conversation.id);
      onConversation?.(created.conversation.id);
    } catch (reason) {
      pendingRef.current = null;
      setCreateError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCreating(false);
    }
  }

  function resetSession() {
    pendingRef.current = null;
    setConversationId("");
    setSeedConversation(null);
    setCreateError("");
  }

  const conversation =
    session.value ??
    (seedConversation && seedConversation.id === conversationId
      ? seedConversation
      : null);

  return {
    conversationId,
    conversation,
    live: session.live,
    busy: creating || session.live.running,
    error: createError || session.error || session.live.error,
    contextEnabled,
    setContextEnabled,
    sendMessage,
    resetSession,
    reload: session.reload,
  };
}
