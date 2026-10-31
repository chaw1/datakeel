import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { objectHref } from "../object/navigation";

import { knowledgeIntentLabels, knowledgeKindLabels } from "./knowledgeLabels";
import { knowledgeReason } from "./reasonText";

import type {
  AskAnswer,
  KnowledgeSubject,
  SelectedKnowledgeIntent,
} from "../../api/ask";

export function KnowledgeResolution({
  answer,
  onChooseSubject,
  onChooseIntent,
}: {
  answer: AskAnswer;
  onChooseSubject?: (subject: KnowledgeSubject) => void;
  onChooseIntent?: (intent: SelectedKnowledgeIntent) => void;
}) {
  const { t, locale } = useI18n();
  const isComposing = useCompositionGuard();
  const clarification = answer.status === "clarification";
  const noKnowledge =
    answer.knowledge?.reason_code === "no_knowledge" ||
    answer.knowledge?.reason_code === "pending_links";
  const pending = answer.knowledge?.pending_ambiguous_links ?? 0;
  const pendingOnly = !clarification && noKnowledge && pending > 0;
  const unsupported = answer.knowledge?.reason_code === "unsupported_phrasing";
  const candidates = answer.subject_candidates;
  const intents = (answer.knowledge?.intent_candidates ?? []).filter(
    (intent) => intent !== "related",
  );
  const intentClarification = clarification && intents.length > 0;
  return (
    <section className="ask-candidates">
      <h2>
        {t(
          intentClarification
            ? "knowledgeIntentClarification"
            : clarification
              ? "knowledgeClarification"
              : "knowledgeUnanswerable",
        )}
      </h2>
      <p
        className={
          pendingOnly
            ? "warning-banner"
            : clarification
              ? "ask-clarification-question"
              : "ask-refusal-reason"
        }
      >
        {t(
          intentClarification
            ? "knowledgeChooseIntent"
            : clarification
              ? "knowledgeChoose"
              : pendingOnly
                ? "knowledgePending"
                : noKnowledge
                  ? "knowledgeNoRecords"
                  : unsupported
                    ? "knowledgeUnsupported"
                    : "knowledgeUnknownSubject",
          { count: pending },
        )}
      </p>
      {intentClarification && (
        <div
          className="ask-examples"
          role="group"
          aria-label={t("knowledgeChooseIntent")}
        >
          {intents.slice(0, 3).map((intent) => (
            <button
              key={intent}
              type="button"
              className="button"
              onKeyDown={(event) => {
                if (isComposing(event.nativeEvent)) event.preventDefault();
              }}
              onClick={() => {
                if (!isComposing()) onChooseIntent?.(intent);
              }}
            >
              {t(knowledgeIntentLabels[intent])}
            </button>
          ))}
        </div>
      )}
      {pending > 0 && !pendingOnly && (
        <p className="warning-banner">
          {t("knowledgePending", { count: pending })}
        </p>
      )}
      {!clarification && (
        <details className="ask-detail">
          <summary>{t("askReasonDetail")}</summary>
          <p>{knowledgeReason(answer, t, locale)}</p>
        </details>
      )}
      {!noKnowledge && !intentClarification && (
        <>
          <h3>
            {t(clarification ? "knowledgeCandidates" : "knowledgeClosest")}
          </h3>
          {candidates.length > 0 ? (
            <ul>
              {candidates.map((candidate) => {
                const summary = (
                  <>
                    <strong>{candidate.name}</strong>
                    <span>
                      {t(knowledgeKindLabels[candidate.kind])}
                      {candidate.entity_type
                        ? ` · ${candidate.entity_type}`
                        : ""}
                    </span>
                    <span>
                      {t(
                        candidate.kind === "kg_entity"
                          ? "knowledgeDocumentEntity"
                          : "knowledgeCatalogAsset",
                      )}
                    </span>
                    {candidate.dataset_name && (
                      <span>
                        {t("knowledgeDataset", {
                          name: candidate.dataset_name,
                        })}
                      </span>
                    )}
                  </>
                );
                return (
                  <li key={candidate.asset_ref.asset_id}>
                    {clarification ? (
                      <button
                        type="button"
                        className="ask-candidate"
                        onKeyDown={(event) => {
                          if (isComposing(event.nativeEvent))
                            event.preventDefault();
                        }}
                        onClick={() => {
                          if (!isComposing()) onChooseSubject?.(candidate);
                        }}
                      >
                        {summary}
                      </button>
                    ) : ["metric", "table", "view"].includes(candidate.kind) ? (
                      <a
                        className="ask-candidate"
                        href={objectHref({
                          kind:
                            candidate.kind === "metric" ? "metric" : "table",
                          id: candidate.asset_ref.asset_id,
                        })}
                      >
                        {summary}
                      </a>
                    ) : (
                      <div className="ask-candidate">{summary}</div>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p>{t("knowledgeNoCandidates")}</p>
          )}
        </>
      )}
    </section>
  );
}
