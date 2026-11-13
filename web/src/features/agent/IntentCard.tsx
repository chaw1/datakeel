import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { ChainCard } from "./ChainCard";

import type { IntentResult, PageContext } from "../../api/intents";
import type { LineageTarget } from "../../app/navigation";
import type { MessageKey } from "../../i18n/en";

const kinds: Record<IntentResult["kind"], MessageKey> = {
  plan: "intentPlan",
  answer: "intentAnswer",
  clarify: "intentClarify",
  refuse: "intentRefuse",
  unsupported: "intentUnsupported",
  failed: "intentFailed",
};

/** Render what the one-sentence entry decided: a plan, an answer, a question or a refusal. */
export function IntentCard({
  intent,
  busy,
  context,
  onReply,
  onResolved,
  onOpenReceipt,
}: {
  intent: IntentResult;
  busy: boolean;
  context?: PageContext;
  onReply?: (content: string) => void;
  onResolved: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const [continuation, setContinuation] = useState<{
    sourceId: string;
    result: IntentResult;
  } | null>(null);
  const candidates = intent.clarification?.candidates ?? [];
  const chainId = intent.chain?.id ?? "";
  const activeContinuation =
    continuation && continuation.sourceId === chainId
      ? continuation.result
      : null;
  return (
    <div className={`intent-card intent-${intent.kind}`}>
      <span className="eyebrow">
        {t(kinds[intent.kind])}
        {intent.parser === "model" && ` · ${t("intentByModel")}`}{" "}
        <span className="badge" title={t("intentBetaHint")}>
          {t("intentBeta")}
        </span>
      </span>
      <p className="intent-text">{intent.text}</p>
      {intent.kind === "refuse" && !!intent.missing_scopes?.length && (
        <p>
          {t("intentMissingScopes")}{" "}
          {intent.missing_scopes.map((scope) => (
            <code key={scope}>{scope}</code>
          ))}
        </p>
      )}
      {intent.kind === "clarify" && !!candidates.length && (
        <div
          className="intent-candidates"
          role="group"
          aria-label={t("intentCandidates")}
        >
          {candidates.map((candidate) => (
            <button
              key={candidate.id}
              className="button subtle"
              disabled={busy || !onReply}
              title={candidate.id}
              onClick={() => onReply?.(candidate.id)}
            >
              {candidate.label}
            </button>
          ))}
        </div>
      )}
      {intent.kind === "answer" && intent.answer && (
        <details className="tool-observation">
          <summary>
            {t("intentReadFunction")} · <code>{intent.answer.function}</code>
          </summary>
          <pre>{JSON.stringify(intent.answer.arguments, null, 2)}</pre>
        </details>
      )}
      {intent.kind === "plan" && intent.chain && (
        <ChainCard
          initial={intent.chain}
          busy={busy}
          context={context}
          hasContinuation={activeContinuation !== null}
          onReplanned={(result) => {
            setContinuation({ sourceId: chainId, result });
          }}
          onResolved={onResolved}
          onOpenReceipt={onOpenReceipt}
        />
      )}
      {activeContinuation && (
        <div className="chain-continuation">
          <IntentCard
            intent={activeContinuation}
            busy={busy}
            context={context}
            onReply={onReply}
            onResolved={onResolved}
            onOpenReceipt={onOpenReceipt}
          />
        </div>
      )}
    </div>
  );
}
