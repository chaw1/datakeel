import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import { metricName, understoodQuestion } from "./metricLabels";

import type { AskAnswer } from "../../api/ask";

export function AskHistory({
  answers,
  currentId,
  onReplay,
  disabled = false,
}: {
  answers: AskAnswer[];
  currentId?: string;
  onReplay: (id: string) => void;
  disabled?: boolean;
}) {
  const { t, locale } = useI18n();
  const isComposing = useCompositionGuard();
  if (!answers.length) return null;
  return (
    <section className="ask-history-list" aria-label={t("askSaved")}>
      <h2>
        {t("askSaved")} · {answers.length}
      </h2>
      <p className="ask-muted">{t("askReplayHint")}</p>
      {answers.map((answer) => (
        <article
          className={`ask-replay ${currentId === answer.id ? "is-focused" : ""}`}
          key={answer.id}
        >
          <span className="ask-history-mark" aria-hidden="true">
            ·
          </span>
          <div>
            <strong>{answer.question}</strong>
            <p>
              {answer.metric_card && metricName(answer.metric_card, locale)}{" "}
              {answer.metric_card &&
                t("askVersion", {
                  version: answer.metric_card.definition.version,
                })}
            </p>
            <p>
              {t("askUnderstood")}
              {understoodQuestion(answer, locale)}
            </p>
            <code title={answer.id}>{answer.id?.slice(0, 8)}</code>
          </div>
          <button
            className="button"
            type="button"
            disabled={disabled}
            aria-label={
              currentId === answer.id
                ? t("askReplay")
                : `${t("askReplay")}: ${answer.question}`
            }
            onKeyDown={(event) => {
              if (isComposing(event.nativeEvent)) event.preventDefault();
            }}
            onClick={() => {
              if (answer.id && !isComposing()) onReplay(answer.id);
            }}
          >
            {t("askReplay")}
          </button>
        </article>
      ))}
    </section>
  );
}
