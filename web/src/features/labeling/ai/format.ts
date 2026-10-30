import type { components } from "../../../api/generated";
import type { Translate } from "../../../i18n/context";
import type { MessageKey } from "../../../i18n/en";

export type ConfidenceTier = components["schemas"]["TierRate"]["tier"];
export type ObjectRef = components["schemas"]["ObjectRef"];

/** The server's high-risk line: a personal annotator sees their own pre-review from here. */
export const HIGH_RISK = 0.3;

/** Whole-percent text for a 0–1 share, or the fallback when it was not measured. */
export function percent(value: number | null | undefined, fallback: string) {
  return value == null ? fallback : `${String(Math.round(value * 100))}%`;
}

/** A ratio people set by hand keeps one decimal, so 12.5% stays 12.5%. */
export function ratio(value: number) {
  return `${String(Number((value * 100).toFixed(1)))}%`;
}

export const tierMessages: Record<ConfidenceTier, MessageKey> = {
  high: "wbTierHigh",
  medium: "wbTierMedium",
  low: "wbTierLow",
};

const objectMessages: Record<ObjectRef["kind"], MessageKey> = {
  label_set: "wbObjectLabelSet",
  box: "wbObjectBox",
  polygon: "wbObjectPolygon",
  span: "wbObjectSpan",
};

/** Name an object the way the editor's selection list does, counting from one. */
export function objectName(object: ObjectRef, t: Translate) {
  return t(objectMessages[object.kind], { index: object.index + 1 });
}
