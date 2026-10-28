import type { MessageKey } from "../../i18n/en";

export const standardStatuses = [
  ["draft", "stdDraft"],
  ["active", "stdActive"],
  ["deprecated", "stdDeprecated"],
] as const;
export const sensitivityLabels = {
  public: "stdPublic",
  internal: "stdInternal",
  confidential: "stdConfidential",
  restricted: "stdRestricted",
} as const;
export const ruleLabels = {
  type: "stdRuleType",
  length: "stdRuleLength",
  precision: "stdRulePrecision",
  code_list: "stdRuleCodeList",
  range: "stdRuleRange",
  pattern: "stdRulePattern",
  required: "stdRuleRequired",
  unit: "stdRuleUnit",
  sensitivity: "stdRuleSensitivity",
} satisfies Record<string, MessageKey>;
export function percentage(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}
