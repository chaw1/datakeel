import { useI18n } from "../../i18n/useI18n";

import { assertionConcept, assertionValue, stateLabel } from "./assertions";

import type { Assertion } from "../../api/types";

export function AssertionChip({
  assertion,
  showSource = true,
}: {
  assertion: Assertion;
  showSource?: boolean;
}) {
  const { t } = useI18n();
  const value = assertionValue(assertion);
  return (
    <span className={`assertion-chip ${value || "pair"} ${assertion.status}`}>
      <strong>{assertion.predicate}</strong>
      <span>{assertionConcept(assertion)}</span>
      <span>
        {value
          ? t(stateLabel(value))
          : t("evDirectDistance", { distance: assertion.distance ?? 0 })}
      </span>
      {showSource && (
        <small className="assertion-source">
          {assertion.extractor.id} · {assertion.extractor.version}
        </small>
      )}
    </span>
  );
}
