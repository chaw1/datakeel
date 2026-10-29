import { useState } from "react";

import { registerEvaluation } from "../../api/llmData";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import type { TrainingEvaluation } from "../../api/llmData";
import type { FileItem } from "../../api/types";
import type { SubmitEvent } from "react";

export function TrainingEvaluations({
  datasetId,
  versionId,
  files,
  evaluations,
  selected,
  onSelected,
  onRegistered,
}: {
  datasetId: string;
  versionId: string;
  files: FileItem[];
  evaluations: TrainingEvaluation[];
  selected: string[];
  onSelected: (ids: string[]) => void;
  onRegistered: () => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [name, setName] = useState("");
  const [fileIds, setFileIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [registered, setRegistered] = useState(false);
  const candidates = files.filter((file) =>
    /\.(?:jsonl|txt)$/i.test(file.filename),
  );
  async function register(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !fileIds.length || isComposing()) return;
    setBusy(true);
    setError("");
    setRegistered(false);
    try {
      const result = await registerEvaluation(datasetId, {
        name: name.trim(),
        source_dataset_id: datasetId,
        version_id: versionId,
        file_ids: fileIds,
      });
      onSelected([...selected, result.id]);
      onRegistered();
      setRegistered(true);
      setName("");
      setFileIds([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("llmDataFailure"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <fieldset className="llm-data-evaluation-selection">
        <legend>{t("llmDataUseEvaluations")}</legend>
        {!evaluations.length && (
          <p className="muted">{t("llmDataNoEvaluations")}</p>
        )}
        {evaluations.map((evaluation) => (
          <label className="llm-data-checkbox" key={evaluation.id}>
            <input
              type="checkbox"
              checked={selected.includes(evaluation.id)}
              onChange={(event) => {
                onSelected(
                  event.target.checked
                    ? [...selected, evaluation.id]
                    : selected.filter((id) => id !== evaluation.id),
                );
              }}
            />
            {evaluation.name}
          </label>
        ))}
      </fieldset>
      <details>
        <summary>{t("llmDataEvaluationTitle")}</summary>
        <p className="muted">{t("llmDataEvaluationHint")}</p>
        {!candidates.length ? (
          <p>{t("llmDataNoEvaluationFiles")}</p>
        ) : (
          <form
            className="llm-data-evaluation-form"
            onSubmit={(event) => void register(event)}
          >
            <label>
              {t("llmDataEvaluationName")}
              <input
                value={name}
                required
                disabled={busy}
                onChange={(event) => {
                  setName(event.target.value);
                }}
              />
            </label>
            <fieldset disabled={busy}>
              <legend>{t("llmDataEvaluationFiles")}</legend>
              {candidates.map((file) => (
                <label className="llm-data-checkbox" key={file.id}>
                  <input
                    type="checkbox"
                    checked={fileIds.includes(file.id)}
                    onChange={(event) => {
                      setFileIds(
                        event.target.checked
                          ? [...fileIds, file.id]
                          : fileIds.filter((id) => id !== file.id),
                      );
                    }}
                  />
                  {file.filename}
                </label>
              ))}
            </fieldset>
            <button
              type="submit"
              className="button"
              disabled={busy || !name.trim() || !fileIds.length || !versionId}
            >
              {t("llmDataRegisterEvaluation")}
            </button>
          </form>
        )}
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        {registered && <p role="status">{t("llmDataEvaluationRegistered")}</p>}
      </details>
    </>
  );
}
