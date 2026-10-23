import { FootnoteReference } from "../../components/FootnoteReference";
import { TriState } from "../../components/TriState";
import { useI18n } from "../../i18n/useI18n";

import { assertionConcept, assertionValue } from "./assertions";
import { concepts, matrixPredicates, reviewOrder, sourceId } from "./matrix";

import type { EvidenceSample } from "../../api/types";
import type { FootnoteItem } from "../../components/Footnotes";

const predicateLabels = {
  mentions: "evMentions",
  annotated_as: "evAnnotated",
  label_gap: "evGapColumn",
} as const;
export function AssertionMatrix({
  sample,
  activeId,
  onActive,
  sources,
  onInspect,
}: {
  sample: EvidenceSample;
  activeId: string;
  onActive: (id: string) => void;
  sources: FootnoteItem[];
  onInspect: () => void;
}) {
  const { t } = useI18n();
  const names = concepts(sample);
  return (
    <table className="assertion-matrix" aria-label={t("evMatrix")}>
      <thead>
        <tr>
          <th aria-label={t("evConcept")} />
          {matrixPredicates.map((predicate) => {
            const assertion = sample.assertions.find(
              (item) => item.predicate === predicate,
            );
            const index = assertion
              ? sources.findIndex(
                  (source) => source.id === sourceId(sample, assertion),
                )
              : -1;
            return (
              <th key={predicate}>
                {t(predicateLabels[predicate])}
                {index >= 0 && (
                  <FootnoteReference item={sources[index]} index={index} />
                )}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {names.slice(0, 3).map((concept, index) => (
          <tr
            key={concept}
            data-anchor-id={concept}
            data-anchor-number={index + 1}
            className={activeId === concept ? "is-linked" : ""}
          >
            <th scope="row">
              <sup>{index + 1}</sup> {concept}
            </th>
            {matrixPredicates.map((predicate) => {
              const assertion = reviewOrder(sample.assertions).find(
                (item) =>
                  item.predicate === predicate &&
                  assertionConcept(item) === concept,
              );
              return (
                <td key={predicate}>
                  <button
                    type="button"
                    className={`matrix-cell ${assertion?.status ?? "missing"}`}
                    aria-label={`${concept} · ${t(predicateLabels[predicate])}`}
                    onMouseEnter={() => {
                      onActive(concept);
                    }}
                    onMouseLeave={() => {
                      onActive("");
                    }}
                    onFocus={() => {
                      onActive(concept);
                    }}
                    onBlur={() => {
                      onActive("");
                    }}
                    onClick={onInspect}
                  >
                    <TriState
                      value={assertion ? assertionValue(assertion) : null}
                      accepted={assertion?.status === "accepted"}
                    />
                    {assertion?.confidence != null &&
                      assertion.confidence < 1 && (
                        <small>{Math.round(assertion.confidence * 100)}%</small>
                      )}
                  </button>
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
