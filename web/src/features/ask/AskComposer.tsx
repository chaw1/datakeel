import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import type { AskRequest } from "../../api/ask";

const examples = [
  ["askExampleRetail", "askQuestionRetail"],
  ["askExampleAmbiguous", "askQuestionAmbiguous"],
  ["askExampleUnavailable", "askQuestionUnavailable"],
] as const;

export function AskComposer({
  busy,
  onSubmit,
  initialQuestion = "",
  initialMetricId,
}: {
  busy: boolean;
  initialQuestion?: string;
  initialMetricId?: string;
  onSubmit: (request: AskRequest) => void;
}) {
  const { t } = useI18n();
  const [question, setQuestion] = useState(initialQuestion);
  const [metricId, setMetricId] = useState(initialMetricId);
  const isComposing = useCompositionGuard();
  const [reference, setReference] = useState("2026-10-01");
  return (
    <form
      className="card ask-composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (isComposing() || busy || !question.trim() || !reference) return;
        onSubmit({
          actor: "local-user",
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
        disabled={busy}
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
            disabled={busy}
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
            disabled={busy}
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
          disabled={busy || !question.trim() || !reference}
        >
          {t(busy ? "askWorking" : "askSubmit")}
        </button>
      </div>
    </form>
  );
}
