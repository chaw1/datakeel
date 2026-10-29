import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import type { AskRequest } from "../../api/ask";

const examples = [
  ["askExampleRetail", "askQuestionRetail"],
  ["askExampleAmbiguous", "askQuestionAmbiguous"],
  ["askExampleUnavailable", "askQuestionUnavailable"],
  ["askExampleOwner", "askQuestionOwner"],
  ["askExampleUpstream", "askQuestionUpstream"],
  ["askExampleDownstream", "askQuestionDownstream"],
] as const;

export function AskComposer({
  busy,
  disabled = false,
  onSubmit,
  initialQuestion = "",
  initialMetricId,
  onActorChange,
  initialActor = "local-user",
}: {
  busy: boolean;
  disabled?: boolean;
  initialQuestion?: string;
  initialMetricId?: string;
  onActorChange?: (actor: string) => void;
  initialActor?: string;
  onSubmit: (request: AskRequest) => void;
}) {
  const { t } = useI18n();
  const waiting = busy || disabled;
  const [actor, setActor] = useState(initialActor);
  const [question, setQuestion] = useState(initialQuestion);
  const [metricId, setMetricId] = useState(initialMetricId);
  const isComposing = useCompositionGuard();
  const [reference, setReference] = useState("2026-10-01");
  return (
    <form
      className="card ask-composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (
          isComposing() ||
          waiting ||
          !question.trim() ||
          !reference ||
          !actor.trim()
        )
          return;
        onSubmit({
          actor: actor.trim(),
          ...(metricId ? { metric_id: metricId } : {}),
          question: question.trim().normalize("NFC"),
          reference_instant: `${reference}T00:00:00Z`,
        });
      }}
    >
      {metricId && (
        <p className="ask-pinned">
          {t("askPinned")}: <code>{metricId}</code>
          <button
            type="button"
            onClick={() => {
              setMetricId(undefined);
            }}
          >
            {t("askUnpin")}
          </button>
        </p>
      )}
      <label htmlFor="ask-actor">{t("assetActor")}</label>
      <input
        className="ask-actor"
        id="ask-actor"
        value={actor}
        required
        disabled={waiting}
        onChange={(event) => {
          setActor(event.target.value);
          onActorChange?.(event.target.value.trim());
        }}
      />
      <p className="muted">{t("assetActorHelp")}</p>
      <label htmlFor="ask-question">{t("askQuestion")}</label>
      <textarea
        onKeyDown={(event) => {
          if (event.key === "Enter" && isComposing(event.nativeEvent))
            event.preventDefault();
        }}
        id="ask-question"
        value={question}
        rows={3}
        maxLength={2000}
        required
        disabled={waiting}
        placeholder={t("askPlaceholder")}
        onChange={(event) => {
          setQuestion(event.target.value);
        }}
      />
      <div className="ask-examples" role="group" aria-label={t("askExamples")}>
        <span>{t("askExamples")}</span>
        {examples.map(([label, value]) => (
          <button
            key={label}
            className="ask-example"
            type="button"
            disabled={waiting}
            onClick={() => {
              setQuestion(t(value));
              setMetricId(undefined);
              document.getElementById("ask-question")?.focus();
            }}
          >
            {t(label)}
          </button>
        ))}
      </div>
      <div className="ask-composer-footer">
        <div className="ask-reference">
          <label htmlFor="ask-reference">{t("askReference")}</label>
          <input
            onKeyDown={(event) => {
              if (event.key === "Enter" && isComposing(event.nativeEvent))
                event.preventDefault();
            }}
            id="ask-reference"
            type="date"
            value={reference}
            min="0001-01-01"
            max="9999-12-31"
            required
            disabled={waiting}
            aria-describedby="ask-reference-hint"
            onChange={(event) => {
              setReference(event.target.value);
            }}
          />
          <p id="ask-reference-hint">{t("askReferenceHint")}</p>
        </div>
        <button
          onKeyDown={(event) => {
            if (event.key === "Enter" && isComposing(event.nativeEvent))
              event.preventDefault();
          }}
          type="submit"
          className="button primary"
          disabled={waiting || !question.trim() || !reference || !actor.trim()}
        >
          {t(busy ? "askWorking" : "askSubmit")}
        </button>
      </div>
    </form>
  );
}
