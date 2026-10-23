import { useState, useSyncExternalStore } from "react";

import { askData, replayAnswer } from "../api/ask";
import { AskAnswerView } from "../features/ask/AskAnswerView";
import { AskComposer } from "../features/ask/AskComposer";
import { AskHistory } from "../features/ask/AskHistory";
import { useI18n } from "../i18n/useI18n";
import { useCompositionGuard } from "../lib/useCompositionGuard";

import "../features/ask/ask.css";

import type { AskAnswer, AskRequest } from "../api/ask";
import type { LineageTarget } from "../app/navigation";

function subscribeHash(callback: () => void) {
  window.addEventListener("hashchange", callback);
  return () => {
    window.removeEventListener("hashchange", callback);
  };
}

type AskOperation = { request: AskRequest } | { answerId: string };

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
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastOperation, setLastOperation] = useState<AskOperation | null>(null);
  async function perform(operation: AskOperation) {
    if (busy || isComposing()) return;
    setBusy(true);
    setError("");
    setAnswer(null);
    setLastOperation(operation);
    try {
      const next =
        "request" in operation
          ? await askData(operation.request)
          : await replayAnswer(operation.answerId);
      setAnswer(next);
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
      <AskComposer
        key={hash}
        initialQuestion={prefill.get("question") ?? ""}
        initialMetricId={prefill.get("metric") ?? undefined}
        busy={busy}
        onSubmit={(request) => {
          void perform({
            request: { ...request, session_id: answer?.session_id },
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
            onChooseMetric={(metricId) => {
              void perform({
                request: {
                  actor:
                    lastOperation && "request" in lastOperation
                      ? lastOperation.request.actor
                      : "local-user",
                  question: answer.question,
                  reference_instant: answer.reference_instant,
                  session_id: answer.session_id,
                  metric_id: metricId,
                },
              });
            }}
          />
          <AskHistory
            answers={savedAnswers}
            currentId={answer.id}
            onReplay={(id) => {
              void perform({ answerId: id });
            }}
          />
        </>
      )}
      {!answer && !busy && !error && (
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
