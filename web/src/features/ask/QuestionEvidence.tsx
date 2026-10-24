import { useI18n } from "../../i18n/useI18n";

import type { AskMatch } from "../../api/ask";

const kinds = {
  exact: "askMatchExact",
  synonym: "askMatchSynonym",
  prefix: "askMatchPrefix",
  dimension_value: "askMatchDimension",
  time: "askMatchTime",
  identifier: "askMatchIdentifier",
  kg_entity: "askMatchEntity",
  role: "askMatchRole",
} as const;

function questionSegments(question: string, matches: AskMatch[]) {
  const characters = Array.from(question.normalize("NFC"));
  const valid = matches.filter(
    (match) =>
      match.start >= 0 &&
      match.end <= characters.length &&
      match.end > match.start,
  );
  const boundaries = [
    ...new Set([
      0,
      characters.length,
      ...valid.flatMap((match) => [match.start, match.end]),
    ]),
  ].sort((first, second) => first - second);
  return boundaries.slice(0, -1).map((start, index) => {
    const end = boundaries[index + 1];
    return {
      start,
      text: characters.slice(start, end).join(""),
      matches: valid.filter(
        (match) => match.start <= start && match.end >= end,
      ),
    };
  });
}

export function QuestionEvidence({
  question,
  matches,
}: {
  question: string;
  matches: AskMatch[];
}) {
  const { t } = useI18n();
  return (
    <section className="ask-question-evidence" aria-label={t("askMatched")}>
      <h3>{t("askMatched")}</h3>
      <p className="ask-highlighted-question">
        {questionSegments(question, matches).map((segment) =>
          segment.matches.length ? (
            <mark
              className="ask-term recognized"
              key={segment.start}
              title={segment.matches.map((match) => match.source).join(" · ")}
            >
              {segment.text}
            </mark>
          ) : (
            <span className="ask-term unrecognized" key={segment.start}>
              {segment.text}
            </span>
          ),
        )}
      </p>
      {matches.length ? (
        <details className="ask-detail">
          <summary>{t("askMatchSources")}</summary>
          <ul className="ask-match-list">
            {matches.map((match, index) => (
              <li key={`${match.source}-${String(index)}`}>
                <strong>{match.text}</strong>
                <span>{t(kinds[match.match_kind])}</span>
                <code>{match.source}</code>
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <p className="ask-muted">{t("askNoMatches")}</p>
      )}
    </section>
  );
}
