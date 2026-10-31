import { localizedObjectName } from "../../i18n/graphCatalogNames";

import type { AskAnswer, AskMetric, KnowledgeAnswer } from "../../api/ask";
import type { Locale } from "../../i18n/context";

export function metricName(metric: AskMetric, locale: Locale): string {
  return localizedObjectName(
    "metric",
    metric.definition.name,
    locale,
    metric.definition.english_name,
  );
}

export function metricOwner(metric: AskMetric, locale: Locale): string {
  return localizedObjectName(
    "owner",
    metric.definition.owner,
    locale,
    metric.owner_english_name,
  );
}

type KnowledgeSubject = NonNullable<KnowledgeAnswer["subject"]>;

/** A recognised subject by its registered English name in English, else as registered. */
export function subjectName(subject: KnowledgeSubject, locale: Locale): string {
  return localizedObjectName(
    subject.kind,
    subject.name,
    locale,
    subject.english_name,
  );
}

/**
 * How the question was understood, in the interface language. Answers saved before the
 * English wording existed fall back to the question as asked, never the Chinese wording.
 */
export function understoodQuestion(answer: AskAnswer, locale: Locale): string {
  const interpreted =
    locale === "en"
      ? answer.interpreted_question_en
      : answer.interpreted_question;
  return interpreted || answer.question;
}
