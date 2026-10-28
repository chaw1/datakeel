import { useEffect, useState, useSyncExternalStore } from "react";

import { askData, openAskConversation, replayAnswer } from "../api/ask";
import { AskAnswerView } from "../features/ask/AskAnswerView";
import { AskComposer } from "../features/ask/AskComposer";
import { AskConversations } from "../features/ask/AskConversations";
import { AskHistory } from "../features/ask/AskHistory";
import { useI18n } from "../i18n/useI18n";
import { useCompositionGuard } from "../lib/useCompositionGuard";

import "../features/ask/ask.css";

import type { AskAnswer, AskConversation, AskRequest } from "../api/ask";
import type { LineageTarget } from "../app/navigation";

function subscribeHash(callback: () => void) {
  window.addEventListener("hashchange", callback);
  return () => {
    window.removeEventListener("hashchange", callback);
  };
}

type AskOperation = { request: AskRequest } | { answerId: string };
const conversationKey = "datakeel.ask.conversation";
const actorKey = "datakeel.ask.actor";

export function AskPage({
  onOpenReceipt,
}: {
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const hash = useSyncExternalStore(subscribeHash, () => window.location.hash);
  const prefill = new URLSearchParams(hash.split("?")[1]);
  const isComposing = useCompositionGuard();
  const [savedAnswers, setSavedAnswers] = useState<AskAnswer[]>([]);
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [initialConversation] = useState(() => ({
    id: sessionStorage.getItem(conversationKey),
    actor: sessionStorage.getItem(actorKey) ?? "local-user",
    failureMessage: t("askError"),
  }));
  const [conversationId, setConversationId] = useState<string | undefined>(
    initialConversation.id ?? undefined,
  );
  const [actor, setActor] = useState(initialConversation.actor);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversationBusy, setConversationBusy] = useState(
    Boolean(initialConversation.id),
  );
  const waiting = busy || conversationBusy;
  const [lastOperation, setLastOperation] = useState<AskOperation | null>(null);
  useEffect(() => {
    if (!initialConversation.id) return;
    let active = true;
    void openAskConversation(initialConversation.id, initialConversation.actor)
      .then((conversation) => {
        if (!active) return;
        setSavedAnswers([...conversation.turns].reverse());
        setAnswer(conversation.turns.at(-1) ?? null);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        sessionStorage.removeItem(conversationKey);
        setConversationId(undefined);
        setError(
          reason instanceof Error
            ? reason.message
            : initialConversation.failureMessage,
        );
      })
      .finally(() => {
        if (active) setConversationBusy(false);
      });
    return () => {
      active = false;
    };
  }, [initialConversation]);
  function openConversation(conversation: AskConversation) {
    setConversationId(conversation.id);
    sessionStorage.setItem(conversationKey, conversation.id);
    sessionStorage.setItem(actorKey, actor);
    setSavedAnswers([...conversation.turns].reverse());
    setAnswer(conversation.turns.at(-1) ?? null);
    setError("");
    setLastOperation(null);
  }
  function newConversation() {
    setConversationId(undefined);
    sessionStorage.removeItem(conversationKey);
    setAnswer(null);
    setSavedAnswers([]);
    setLastOperation(null);
    setError("");
  }
  const chosenIntent =
    lastOperation && "request" in lastOperation
      ? lastOperation.request.knowledge_intent
      : answer?.knowledge?.reason_code === "ambiguous_subject" &&
          answer.knowledge.intent !== "related"
        ? answer.knowledge.intent
        : undefined;
  async function perform(operation: AskOperation) {
    if (waiting || isComposing()) return;
    setBusy(true);
    setError("");
    setAnswer(null);
    setLastOperation(operation);
    try {
      const next =
        "request" in operation
          ? await askData(operation.request)
          : await replayAnswer(operation.answerId, actor);
      setAnswer(next);
      if (next.conversation_id) {
        setConversationId(next.conversation_id);
        sessionStorage.setItem(conversationKey, next.conversation_id);
        sessionStorage.setItem(actorKey, actor);
      }
      if (next.id)
        setSavedAnswers((previous) => [
          next,
          ...previous.filter((item) => item.id !== next.id),
        ]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("askError"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ask-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("askNav")}</span>
          <h1>
            {t("askTitle")} · {savedAnswers.length}
          </h1>
        </div>
      </div>
      <AskConversations
        key={actor}
        actor={actor}
        activeId={conversationId}
        disabled={waiting}
        onBusyChange={setConversationBusy}
        onOpen={openConversation}
        onNew={newConversation}
        onDeleted={(id) => {
          if (id === conversationId) newConversation();
        }}
      />
      <AskComposer
        key={hash}
        initialQuestion={prefill.get("question") ?? ""}
        initialMetricId={prefill.get("metric") ?? undefined}
        initialActor={actor}
        busy={busy}
        disabled={conversationBusy}
        onActorChange={(nextActor) => {
          setActor(nextActor);
          if (nextActor !== actor) newConversation();
        }}
        onSubmit={(request) => {
          void perform({
            request: {
              ...request,
              session_id: answer?.session_id,
              ...(conversationId ? { conversation_id: conversationId } : {}),
            },
          });
        }}
      />
      {busy && (
        <div className="card ask-loading" role="status">
          <span className="ask-loading-dot" />
          {t(
            lastOperation && "answerId" in lastOperation
              ? "askReplaying"
              : "askWorking",
          )}
        </div>
      )}
      {error && (
        <div className="error-banner" role="alert">
          <div>
            <strong>{t("askError")}</strong>
            <p>{error}</p>
          </div>
          <button
            className="button"
            type="button"
            onClick={() => {
              if (lastOperation) void perform(lastOperation);
            }}
          >
            {t("askRetry")}
          </button>
        </div>
      )}
      {answer && (
        <>
          <AskAnswerView
            answer={answer}
            onOpenReceipt={onOpenReceipt}
            onChooseProfileDataset={(datasetId) => {
              void perform({
                request: {
                  actor:
                    lastOperation && "request" in lastOperation
                      ? lastOperation.request.actor
                      : actor,
                  question: answer.question,
                  reference_instant: answer.reference_instant,
                  session_id: answer.session_id,
                  ...(conversationId
                    ? { conversation_id: conversationId }
                    : {}),
                  subject_id: datasetId,
                },
              });
            }}
            onChooseIntent={(intent) => {
              void perform({
                request: {
                  actor:
                    lastOperation && "request" in lastOperation
                      ? lastOperation.request.actor
                      : actor,
                  question: answer.question,
                  reference_instant: answer.reference_instant,
                  session_id: answer.session_id,
                  ...(conversationId
                    ? { conversation_id: conversationId }
                    : {}),
                  subject_id: answer.knowledge?.subject?.asset_ref.asset_id,
                  knowledge_intent: intent,
                },
              });
            }}
            onChooseSubject={(subject) => {
              void perform({
                request: {
                  actor:
                    lastOperation && "request" in lastOperation
                      ? lastOperation.request.actor
                      : actor,
                  question: answer.question,
                  reference_instant: answer.reference_instant,
                  session_id: answer.session_id,
                  ...(conversationId
                    ? { conversation_id: conversationId }
                    : {}),
                  subject_id: subject.asset_ref.asset_id,
                  ...(chosenIntent ? { knowledge_intent: chosenIntent } : {}),
                },
              });
            }}
            onChooseMetric={(metricId) => {
              void perform({
                request: {
                  actor:
                    lastOperation && "request" in lastOperation
                      ? lastOperation.request.actor
                      : actor,
                  question: answer.question,
                  reference_instant: answer.reference_instant,
                  session_id: answer.session_id,
                  ...(conversationId
                    ? { conversation_id: conversationId }
                    : {}),
                  metric_id: metricId,
                },
              });
            }}
          />
          <AskHistory
            answers={savedAnswers}
            disabled={waiting}
            currentId={answer.id}
            onReplay={(id) => {
              void perform({ answerId: id });
            }}
          />
        </>
      )}
      {!answer && !waiting && !error && (
        <div className="card ask-empty">
          <span className="ask-empty-symbol" aria-hidden="true">
            ?
          </span>
          <h2>{t("askEmptyTitle")}</h2>
          <p>{t("askEmptyBody")}</p>
        </div>
      )}
    </div>
  );
}
