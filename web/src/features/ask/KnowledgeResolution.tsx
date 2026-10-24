import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { objectHref } from "../object/navigation";

import type { AskAnswer, KnowledgeSubject } from "../../api/ask";

const kindLabels = {
  metric: "knowledgeMetric",
  table: "knowledgeTable",
  view: "knowledgeView",
  owner: "knowledgeRole",
  kg_entity: "knowledgeEntity",
} as const;

export function KnowledgeResolution({
  answer,
  onChooseSubject,
}: {
  answer: AskAnswer;
  onChooseSubject?: (subject: KnowledgeSubject) => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const clarification = answer.status === "clarification";
  const noKnowledge =
    answer.knowledge?.reason_code === "no_knowledge" ||
    answer.knowledge?.reason_code === "pending_links";
  const pending = answer.knowledge?.pending_ambiguous_links ?? 0;
  const pendingOnly = !clarification && noKnowledge && pending > 0;
  const unsupported = answer.knowledge?.reason_code === "unsupported_phrasing";
  const candidates = answer.subject_candidates;
  return (
    <section className="ask-candidates">
      <h2>
        {t(clarification ? "knowledgeClarification" : "knowledgeUnanswerable")}
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
          clarification
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
      {pending > 0 && !pendingOnly && (
        <p className="warning-banner">
          {t("knowledgePending", { count: pending })}
        </p>
      )}
      {!clarification && (
        <details className="ask-detail">
          <summary>{t("askReasonDetail")}</summary>
          <p>{answer.message}</p>
        </details>
      )}
      {!noKnowledge && (
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
                      {t(kindLabels[candidate.kind])}
                      {candidate.entity_type
                        ? ` · ${candidate.entity_type}`
                        : ""}
                    </span>
                    {candidate.dataset_name && (
                      <span>
                        {t("knowledgeDataset", {
                          name: candidate.dataset_name,
                        })}
                      </span>
                    )}
                    <code>{candidate.asset_ref.asset_id}</code>
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
