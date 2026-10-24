import { Footnotes } from "../../components/Footnotes";
import { useI18n } from "../../i18n/useI18n";

import { answerFootnotes } from "./answerFootnotes";
import { QuestionEvidence } from "./QuestionEvidence";

import type { AskAnswer } from "../../api/ask";
import type { LineageTarget } from "../../app/navigation";

export function AnswerProvenance({
  answer,
  onOpenReceipt,
}: {
  answer: AskAnswer;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const lineage = answer.lineage;
  const footnotes =
    answer.status === "answered" ? answerFootnotes(answer, t) : [];
  if (answer.answer_kind === "knowledge" && !lineage && !footnotes.length)
    return null;
  return (
    <section className="ask-provenance" aria-label={t("askProvenance")}>
      <div className="ask-section-heading">
        <h2>{t("askProvenance")}</h2>
        {lineage && (
          <button
            className="button"
            type="button"
            onClick={() => {
              onOpenReceipt({
                assetId: lineage.asset_id,
                includeCatalog: true,
              });
            }}
          >
            {t("askLineage")}
          </button>
        )}
      </div>
      {answer.answer_kind !== "knowledge" && (
        <QuestionEvidence question={answer.question} matches={answer.matches} />
      )}
      {footnotes.length > 0 && <Footnotes items={footnotes} />}
    </section>
  );
}
