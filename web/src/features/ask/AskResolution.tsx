import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { objectHref } from "../object/navigation";

import type { AskAnswer } from "../../api/ask";

export function AskResolution({
  answer,
  onChooseMetric,
}: {
  answer: AskAnswer;
  onChooseMetric?: (id: string) => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [todo, setTodo] = useState("");
  const clarification = answer.status === "clarification";
  const reasonKey = /时间|time|date/i.test(answer.message)
    ? "askReasonTime"
    : /目录对象|字段|unresolved|field/i.test(answer.message)
      ? "askReasonFields"
      : /暂时无法执行|ExecutionError|ValidationError|NotFoundError/i.test(
            answer.message,
          )
        ? "askReasonExecution"
        : /尚未解析/i.test(answer.message)
          ? "askReasonConditions"
          : "askReasonMissing";
  return (
    <section className="ask-candidates">
      <h2>{t(clarification ? "askClarification" : "askUnanswerable")}</h2>
      {clarification ? (
        <p className="ask-clarification-question">
          {t("askClarificationQuestion")}
        </p>
      ) : (
        <>
          <p className="ask-refusal-reason">{t(reasonKey)}</p>
          <details className="ask-detail">
            <summary>{t("askReasonDetail")}</summary>
            <p>{answer.message}</p>
          </details>
        </>
      )}
      <h3>{t(clarification ? "askCandidates" : "askClosest")}</h3>
      {answer.candidates.length ? (
        <ul>
          {answer.candidates.map(({ definition }) => (
            <li key={definition.id}>
              {clarification ? (
                <button
                  type="button"
                  className="ask-candidate"
                  onKeyDown={(event) => {
                    if (isComposing(event.nativeEvent)) event.preventDefault();
                  }}
                  onClick={() => {
                    if (!isComposing()) onChooseMetric?.(definition.id);
                  }}
                >
                  <strong>{definition.name}</strong>
                  <span>{definition.description}</span>
                  <code>{`${definition.measure.aggregation}(${definition.measure.column})`}</code>
                  <span>
                    {t("askVersion", { version: definition.version })} ·{" "}
                    {t("askOwner")}: {definition.owner}
                  </span>
                </button>
              ) : (
                <>
                  <a href={objectHref({ kind: "metric", id: definition.id })}>
                    {definition.name}
                  </a>
                  <p>{definition.description}</p>
                  <span className="ask-muted">
                    {t("askVersion", { version: definition.version })} ·{" "}
                    {t("askOwner")}: {definition.owner}
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p>{t("askNoCandidates")}</p>
      )}
      {!clarification && (
        <div className="ask-todo">
          <button
            type="button"
            className="button"
            onKeyDown={(event) => {
              if (isComposing(event.nativeEvent)) event.preventDefault();
            }}
            onClick={() => {
              if (isComposing()) return;
              const owners = [
                ...new Set(
                  answer.candidates.map(({ definition }) => definition.owner),
                ),
              ].join(", ");
              setTodo(
                `${t("askTodoTitle")}\n${t("askQuestion")}: ${answer.question}\n${t("askReasonDetail")}: ${answer.message}\n${t("askOwner")}: ${owners || t("askNoCandidates")}`,
              );
            }}
          >
            {t("askRequestMetric")}
          </button>
          <p className="ask-muted">{t("askTodoHint")}</p>
          {todo && (
            <label>
              {t("askTodoTitle")}
              <textarea
                className="ask-todo-text"
                value={todo}
                readOnly
                rows={5}
              />
            </label>
          )}
        </div>
      )}
    </section>
  );
}
