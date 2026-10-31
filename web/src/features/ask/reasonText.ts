import { subjectName } from "./metricLabels";

import type { AskAnswer } from "../../api/ask";
import type { components } from "../../api/generated";
import type { Locale, Translate } from "../../i18n/context";
import type { MessageKey } from "../../i18n/en";

type ReasonCode = components["schemas"]["AskReason"]["code"];
type ProfileCode = NonNullable<
  components["schemas"]["ProfileAnswer"]["reason_code"]
>;

const metricReasons: Record<ReasonCode, MessageKey> = {
  ambiguous_metric: "askWhyAmbiguousMetric",
  unresolved_metric: "askWhyUnresolvedMetric",
  time_unparsed: "askWhyTimeUnparsed",
  generic_metric: "askWhyGenericMetric",
  no_metric: "askWhyNoMetric",
  selected_metric_missing: "askWhySelectedMetricMissing",
  selected_metric_unresolved: "askWhySelectedMetricUnresolved",
  execution_failed: "askWhyExecutionFailed",
  time_not_understood: "askWhyTimeNotUnderstood",
  unsupported_calculation: "askWhyUnsupportedCalculation",
  unclear_condition: "askWhyUnclearCondition",
  share_needs_grouping: "askWhyShareNeedsGrouping",
  comparison_period_mismatch: "askWhyComparisonPeriodMismatch",
  year_over_year_needs_range: "askWhyYearOverYearNeedsRange",
  previous_period_needs_range: "askWhyPreviousPeriodNeedsRange",
  same_period_needs_range: "askWhySamePeriodNeedsRange",
  followup_time_unparsed: "askWhyFollowupTimeUnparsed",
  followup_metric_unavailable: "askWhyFollowupMetricUnavailable",
  followup_dimensions_unclear: "askWhyFollowupDimensionsUnclear",
  followup_comparison_unclear: "askWhyFollowupComparisonUnclear",
  followup_change_unclear: "askWhyFollowupChangeUnclear",
};

const profileReasons: Record<ProfileCode, MessageKey> = {
  no_profile: "askProfileWhyNoProfile",
  unknown_subject: "askProfileWhyUnknownSubject",
  unknown_column: "askProfileWhyUnknownColumn",
  ambiguous_dataset: "askProfileWhyAmbiguousDataset",
  incomplete_profile: "askProfileWhyIncompleteProfile",
  no_recorded_gaps: "askProfileWhyNoRecordedGaps",
};

function quoted(items: readonly string[], locale: Locale): string {
  return locale === "zh"
    ? items.map((item) => `「${item}」`).join("")
    : items.map((item) => `“${item}”`).join(", ");
}

/**
 * The recorded reason of a metric refusal or clarification in the interface language. Answers
 * stored before reasons had codes show their message as recorded.
 */
export function metricReason(
  answer: AskAnswer,
  t: Translate,
  locale: Locale,
): string {
  const reason = answer.reason;
  if (!reason) return answer.message;
  const details = [
    ...reason.notes,
    ...reason.fragments.map((fragment) =>
      t("askWhyNotUnderstood", { fragment: quoted([fragment], locale) }),
    ),
  ];
  return t(metricReasons[reason.code], {
    fragments: quoted(reason.fragments, locale),
    notes: reason.notes.join("; "),
    details: details.join("; "),
  });
}

/** Why the system and documents could not answer a knowledge question, in the interface language. */
export function knowledgeReason(
  answer: AskAnswer,
  t: Translate,
  locale: Locale,
): string {
  const knowledge = answer.knowledge;
  if (!knowledge?.reason_code) return answer.message;
  if (knowledge.pending_ambiguous_links)
    return t("knowledgeWhyPending", {
      count: knowledge.pending_ambiguous_links,
    });
  const subject = knowledge.subject;
  const name = subject
    ? subjectName(subject, locale)
    : t("knowledgeWhySubject");
  return t(
    subject && subject.kind !== "kg_entity"
      ? "knowledgeWhyMissingCatalog"
      : "knowledgeWhyMissingGraph",
    { name },
  );
}

/** What a time-series profile answer ranked by, or why it could not rank. */
export function profileMessage(answer: AskAnswer, t: Translate): string {
  const profile = answer.profile;
  if (!profile) return answer.message;
  if (profile.reason_code) return t(profileReasons[profile.reason_code]);
  return t(
    profile.sort_by === "gap_count"
      ? "askProfileRankedGapCount"
      : "askProfileRankedDuration",
  );
}
