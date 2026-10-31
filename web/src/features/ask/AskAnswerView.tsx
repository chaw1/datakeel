import { FootnoteReference } from "../../components/FootnoteReference";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";

import { answerFootnotes } from "./answerFootnotes";
import { AnswerProvenance } from "./AnswerProvenance";
import { AskChart } from "./AskChart";
import { AskResolution } from "./AskResolution";
import { KnowledgeAnswerView } from "./KnowledgeAnswerView";
import { KnowledgeResolution } from "./KnowledgeResolution";
import { metricName, understoodQuestion } from "./metricLabels";
import { ProfileAnswerView } from "./ProfileAnswerView";

import type {
  AskAnswer,
  AskResult,
  KnowledgeSubject,
  SelectedKnowledgeIntent,
} from "../../api/ask";
import type { LineageTarget } from "../../app/navigation";
import type { Translate } from "../../i18n/context";

const statusLabels = {
  answered: "askAnswered",
  unanswerable: "askUnanswerable",
  clarification: "askClarification",
} as const;
const knowledgeStatusLabels = {
  answered: "knowledgeAnswered",
  unanswerable: "knowledgeUnanswerable",
  clarification: "knowledgeClarification",
} as const;
const profileStatusLabels = {
  answered: "askProfileAnswered",
  unanswerable: "askProfileUnavailable",
  clarification: "askProfileChoose",
} as const;

function displayValue(
  value: AskResult["rows"][number][number],
  locale: string,
  t: Translate,
) {
  if (value === null) return t("askNull");
  if (typeof value === "boolean") return t(value ? "askTrue" : "askFalse");
  return typeof value === "number"
    ? new Intl.NumberFormat(locale, { maximumFractionDigits: 8 }).format(value)
    : value;
}

export function AskAnswerView({
  answer,
  onOpenReceipt,
  onChooseMetric,
  onChooseSubject,
  onChooseIntent,
  onChooseProfileDataset,
}: {
  answer: AskAnswer;
  onOpenReceipt: (target: LineageTarget) => void;
  onChooseMetric?: (id: string) => void;
  onChooseSubject?: (subject: KnowledgeSubject) => void;
  onChooseIntent?: (intent: SelectedKnowledgeIntent) => void;
  onChooseProfileDataset?: (id: string) => void;
}) {
  const { t, locale } = useI18n();
  const result = answer.result;
  const footnotes = answerFootnotes(answer, t);
  const scalar = result?.rows.length === 1 && result.columns.length === 1;
  const knowledgeAnswer = answer.answer_kind === "knowledge";
  const profileAnswer = answer.answer_kind === "profile";
  const labels = profileAnswer
    ? profileStatusLabels
    : knowledgeAnswer
      ? knowledgeStatusLabels
      : statusLabels;
  const intentClarification =
    knowledgeAnswer &&
    answer.status === "clarification" &&
    (answer.knowledge?.intent_candidates ?? []).length > 0;
  return (
    <article className={`card ask-answer ask-answer-${answer.status}`}>
      <header className="ask-answer-heading">
        <span
          className={`badge ${answer.status === "answered" ? "green" : ""}`}
        >
          {t(
            intentClarification
              ? "knowledgeIntentClarification"
              : labels[answer.status],
          )}
        </span>
        <span className="ask-muted">
          {t("askReferenceUsed")}
          <time dateTime={answer.reference_instant}>
            {t("askUtcTime", {
              time: date(answer.reference_instant, locale, "UTC"),
            })}
          </time>
        </span>
      </header>
      <p className="ask-understood">
        {t("askUnderstood")}
        {understoodQuestion(answer, locale)}
      </p>
      {profileAnswer ? (
        <ProfileAnswerView
          answer={answer}
          onChooseDataset={onChooseProfileDataset}
        />
      ) : knowledgeAnswer ? (
        answer.status === "answered" && answer.knowledge ? (
          <KnowledgeAnswerView knowledge={answer.knowledge} />
        ) : (
          <KnowledgeResolution
            answer={answer}
            onChooseSubject={onChooseSubject}
            onChooseIntent={onChooseIntent}
          />
        )
      ) : answer.status === "answered" ? (
        <>
          <div className="ask-result">
            <span className="eyebrow">
              {answer.metric_card && metricName(answer.metric_card, locale)}
            </span>
            {answer.chart ? (
              <AskChart
                key={answer.id}
                answer={answer}
                chart={answer.chart}
                footnotes={footnotes}
              />
            ) : scalar ? (
              <div className="ask-number-line">
                <output
                  className="ask-scalar answer-number"
                  aria-label={t("askResult")}
                >
                  {displayValue(result.rows[0]?.[0] ?? null, locale, t)}
                </output>
                <span className="ask-answer-references">
                  {footnotes.map((item, index) => (
                    <FootnoteReference
                      item={item}
                      index={index}
                      key={item.id}
                    />
                  ))}
                </span>
              </div>
            ) : result?.rows.length ? (
              <div className="ask-table-scroll">
                <table>
                  <caption>{t("askResults")}</caption>
                  <thead>
                    <tr>
                      {result.columns.map((column) => (
                        <th key={column} scope="col">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {row.map((value, index) => (
                          <td key={index}>
                            {displayValue(value, locale, t)}
                            {typeof value === "number" &&
                              footnotes.map((item, footnoteIndex) => (
                                <FootnoteReference
                                  item={item}
                                  index={footnoteIndex}
                                  key={item.id}
                                />
                              ))}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>{t("askNoRows")}</p>
            )}
            {result?.truncated && (
              <p className="ask-muted">{t("askTruncated")}</p>
            )}
          </div>
          {answer.knowledge && (
            <KnowledgeAnswerView knowledge={answer.knowledge} />
          )}
        </>
      ) : (
        <AskResolution
          key={answer.id ?? answer.question}
          answer={answer}
          onChooseMetric={onChooseMetric}
        />
      )}
      <AnswerProvenance answer={answer} onOpenReceipt={onOpenReceipt} />
    </article>
  );
}
