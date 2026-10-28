import { useState } from "react";

import { submitCustomOperator } from "../../api/customOperators";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import type { CustomOperatorSubmission } from "../../api/customOperators";
import type { ActionPlan } from "../../api/types";

export function SubmissionForm({
  onPrepared,
}: {
  onPrepared: (plan: ActionPlan) => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [modality, setModality] =
    useState<CustomOperatorSubmission["modality"]>("text");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isComposing = useCompositionGuard();
  async function submit() {
    if (busy || isComposing() || !name.trim() || !code.trim()) return;
    setBusy(true);
    setError("");
    try {
      onPrepared(
        await submitCustomOperator({ name: name.trim(), code, modality }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="card custom-submission-form"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <h2>{t("customOperatorSubmit")}</h2>
      <p className="muted">{t("customOperatorImmutable")}</p>
      <div className="custom-form-row">
        <label htmlFor="custom-name">
          {t("customOperatorName")}
          <input
            id="custom-name"
            required
            maxLength={64}
            pattern={"[a-z][a-z0-9_\\-]{0,63}"}
            value={name}
            disabled={busy}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </label>
        <label htmlFor="custom-modality">
          {t("customOperatorModality")}
          <select
            id="custom-modality"
            value={modality}
            disabled={busy}
            onBlur={(event) => {
              setModality(
                event.target.value as CustomOperatorSubmission["modality"],
              );
            }}
            onChange={(event) => {
              setModality(
                event.target.value as CustomOperatorSubmission["modality"],
              );
            }}
          >
            <option value="any">{t("customOperatorAny")}</option>
            <option value="text">{t("customOperatorText")}</option>
            <option value="image">{t("customOperatorImage")}</option>
          </select>
        </label>
      </div>
      <label htmlFor="custom-code">{t("customOperatorCode")}</label>
      <p id="custom-code-hint" className="muted">
        {t("customOperatorCodeHint")}
      </p>
      <textarea
        id="custom-code"
        className="custom-code-input"
        required
        maxLength={65536}
        spellCheck={false}
        aria-describedby="custom-code-hint"
        value={code}
        disabled={busy}
        onChange={(event) => {
          setCode(event.target.value);
        }}
      />
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      <button
        className="button primary"
        type="submit"
        disabled={busy || !name.trim() || !code.trim()}
        onKeyDown={(event) => {
          if (isComposing(event.nativeEvent)) event.preventDefault();
        }}
      >
        {t(busy ? "planWorking" : "customOperatorSubmit")}
      </button>
    </form>
  );
}
