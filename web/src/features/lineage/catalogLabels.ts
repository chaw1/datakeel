import { kindLabels, linkLabels } from "../catalog/values";

import type { Translate } from "../../i18n/context";

export function catalogKindLabel(kind: string, t: Translate) {
  const label = Object.entries(kindLabels).find(([key]) => key === kind)?.[1];
  return label ? t(label) : kind;
}

export function catalogLinkLabel(kind: string, t: Translate) {
  const label = Object.entries(linkLabels).find(([key]) => key === kind)?.[1];
  return label ? t(label) : kind;
}
