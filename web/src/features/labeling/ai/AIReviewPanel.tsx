import { useI18n } from "../../../i18n/useI18n";
import { findingLabels } from "../../annotation/findingLabels";

import { objectName, percent } from "./format";
import "./ai.css";

import type { ObjectRef } from "./format";
import type { components } from "../../../api/generated";
import type { Locale } from "../../../i18n/context";
import type { MessageKey } from "../../../i18n/en";

type AIReview = components["schemas"]["AIReview"];

type RiskReason = AIReview["reasons"][number];

/** Rule names in the interface language; unknown rules show only the server's sentence. */
const reasonLabels: Partial<Record<string, MessageKey>> = {
  ...findingLabels,
  template_violation: "wbAiTemplateViolation",
  prelabel_disagreement: "wbAiDisagreement",
};

/** The server's plain sentence in the interface language; English when no Chinese one came. */
function reasonSentence(reason: RiskReason, locale: Locale) {
  return locale === "zh" && reason.message_zh
    ? reason.message_zh
    : reason.message;
}

const decisions: Record<AIReview["decision"], MessageKey> = {
  review: "wbAiDecisionReview",
  exempt: "wbAiDecisionExempt",
  personal: "wbAiDecisionPersonal",
};

/**
 * The AI pre-review bound to a submitted revision: its risk, what it decided and each rule
 * hit in a plain sentence. Objects a reviewer can see in the editor get a locate button.
 */
export function AIReviewPanel({
  review,
  own = false,
  onLocate,
}: {
  review: AIReview;
  /** The annotator reading their own submission's pre-review, not a reviewer. */
  own?: boolean;
  /** Absent when the editor shows another revision than the one that was scored. */
  onLocate?: (object: ObjectRef) => void;
}) {
  const { t, locale } = useI18n();
  const title = t(own ? "wbAiReviewOwn" : "wbAiReview");
  return (
    <section
      className="card wb-ai-review"
      aria-label={title}
      role={own ? "status" : undefined}
    >
      <h3>{title}</h3>
      <p>
        {t("wbAiRisk", { risk: percent(review.risk, t("wbUnavailable")) })}{" "}
        {review.high_risk && (
          <span className="badge red">{t("wbHighRisk")}</span>
        )}
      </p>
      <p>{t(decisions[review.decision])}</p>
      {review.reasons.length ? (
        <ul className="wb-ai-reasons">
          {review.reasons.map((reason, position) => {
            const label = reasonLabels[reason.code];
            const sentence = reasonSentence(reason, locale);
            return (
              <li key={`${reason.code}:${String(position)}`}>
                <strong>{label ? t(label) : sentence}</strong>{" "}
                {label && sentence && <span>{sentence} </span>}
                <span className="muted">
                  {t("wbAiWeight", { weight: reason.weight.toFixed(2) })}
                </span>
                {reason.objects.length > 0 && (
                  <div className="wb-ai-objects">
                    {reason.objects.map((object) =>
                      onLocate && object.kind !== "label_set" ? (
                        <button
                          type="button"
                          key={`${object.kind}:${String(object.index)}`}
                          onClick={() => {
                            // A fresh request each time, so locating the same object again works.
                            onLocate({ ...object });
                          }}
                        >
                          {t("wbLocate", { object: objectName(object, t) })}
                        </button>
                      ) : (
                        <span key={`${object.kind}:${String(object.index)}`}>
                          {objectName(object, t)}
                        </span>
                      ),
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="muted">{t("wbAiNoReasons")}</p>
      )}
    </section>
  );
}
