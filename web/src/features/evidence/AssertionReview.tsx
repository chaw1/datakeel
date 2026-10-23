import { useI18n } from "../../i18n/useI18n";

import { AssertionChip } from "./AssertionChip";
import { assertionConcept } from "./assertions";

import type { Assertion } from "../../api/types";

export function AssertionReview({
  assertions,
  activeId,
  busy,
  onLocate,
  onDecide,
  activeConcept,
  onHover,
  numbers,
}: {
  assertions: Assertion[];
  activeId: string;
  busy: boolean;
  onLocate: (id: string) => void;
  onDecide: (assertion: Assertion, status: Assertion["status"]) => void;
  activeConcept: string;
  onHover: (id: string) => void;
  numbers: string[];
}) {
  const { t } = useI18n();
  return (
    <section className="assertion-review" aria-label={t("evReview")}>
      <h3>{t("evReview")}</h3>
      {!assertions.length && <p className="muted">{t("evNoAssertions")}</p>}
      {assertions.map((assertion) => (
        <article
          className={`assertion-review-card ${assertion.status}${activeId === assertion.id ? " is-active" : ""}${activeConcept === assertionConcept(assertion) ? " is-linked" : ""}`}
          data-assertion-id={assertion.id}
          data-anchor-id={assertionConcept(assertion) ?? undefined}
          onMouseEnter={() => {
            onHover(assertionConcept(assertion) ?? "");
          }}
          onMouseLeave={() => {
            onHover("");
          }}
          onFocusCapture={() => {
            onHover(assertionConcept(assertion) ?? "");
          }}
          onBlurCapture={() => {
            onHover("");
          }}
          key={assertion.id}
          aria-label={`${assertion.predicate}: ${assertion.id || assertion.producer_event_id}`}
        >
          <div className="section-heading">
            <div>
              <sup>
                {numbers.indexOf(assertionConcept(assertion) ?? "") >= 0
                  ? numbers.indexOf(assertionConcept(assertion) ?? "") + 1
                  : ""}
              </sup>
              <AssertionChip assertion={assertion} showSource={false} />
            </div>
            <span className="badge gray">{t(assertion.status)}</span>
          </div>
          <div className="assertion-review-controls">
            <button
              className="text-button"
              aria-pressed={activeId === assertion.id}
              onClick={() => {
                onLocate(assertion.id || "");
              }}
            >
              {t("evLocate")}
            </button>
            {(
              [
                ["accepted", "evAccept"],
                ["rejected", "evReject"],
                ["candidate", "evRestore"],
              ] as const
            ).map(([status, label]) => (
              <button
                className="button subtle"
                key={status}
                disabled={busy || !assertion.id || assertion.status === status}
                onClick={() => {
                  onDecide(assertion, status);
                }}
              >
                {t(label)}
              </button>
            ))}
          </div>
          <p className="mono small">
            {t("evProducer")}: {assertion.producer_event_id}
          </p>
          <details>
            <summary>{t("evFullAssertion")}</summary>
            <pre>{JSON.stringify(assertion, null, 2)}</pre>
          </details>
        </article>
      ))}
    </section>
  );
}
