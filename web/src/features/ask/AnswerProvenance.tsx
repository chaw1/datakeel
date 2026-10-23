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
      <QuestionEvidence question={answer.question} matches={answer.matches} />
      {answer.status === "answered" && (
        <Footnotes items={answerFootnotes(answer, t)} />
      )}
    </section>
  );
}
