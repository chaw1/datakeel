import type { Assertion, EvidenceSample } from "../../api/types";
import type { MessageKey } from "../../i18n/en";

export function assertionValue(assertion: Assertion) {
  return "value" in assertion.object ? assertion.object.value : null;
}
export function stateLabel(
  value: "present" | "absent" | "unknown",
): MessageKey {
  return value === "present"
    ? "evPresent"
    : value === "absent"
      ? "evAbsent"
      : "evUnknown";
}
export function assertionConcept(assertion: Assertion) {
  return "concept" in assertion.object
    ? assertion.object.concept
    : "asset_id" in assertion.object
      ? assertion.object.asset_id
      : null;
}
export function locators(sample: EvidenceSample, selected?: Assertion) {
  const assertions = selected
    ? [selected]
    : sample.assertions.filter((assertion) => assertion.status !== "rejected");
  const boxes: EvidenceSample["annotation_boxes"] = [];
  const spans: EvidenceSample["caption_spans"] = [];
  for (const assertion of assertions)
    for (const anchor of assertion.anchors) {
      const selector = anchor.selector;
      if (selector && "bbox" in selector)
        boxes.push({
          ...selector,
          concept: assertionConcept(assertion) || assertion.predicate,
        });
      if (selector && "start" in selector) spans.push(selector);
    }
  return { boxes, spans };
}
