import { useState } from "react";

import { registerEvaluation } from "../../api/trainingData";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import type { TrainingEvaluation } from "../../api/trainingData";
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
      setError(reason instanceof Error ? reason.message : t("trainingFailure"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <fieldset className="training-evaluation-selection">
        <legend>{t("trainingUseEvaluations")}</legend>
        {!evaluations.length && (
          <p className="muted">{t("trainingNoEvaluations")}</p>
        )}
        {evaluations.map((evaluation) => (
          <label className="training-checkbox" key={evaluation.id}>
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
        <summary>{t("trainingEvaluationTitle")}</summary>
        <p className="muted">{t("trainingEvaluationHint")}</p>
        {!candidates.length ? (
          <p>{t("trainingNoEvaluationFiles")}</p>
        ) : (
          <form
            className="training-evaluation-form"
            onSubmit={(event) => void register(event)}
          >
            <label>
              {t("trainingEvaluationName")}
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
              <legend>{t("trainingEvaluationFiles")}</legend>
              {candidates.map((file) => (
                <label className="training-checkbox" key={file.id}>
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
              {t("trainingRegisterEvaluation")}
            </button>
          </form>
        )}
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        {registered && <p role="status">{t("trainingEvaluationRegistered")}</p>}
      </details>
    </>
  );
}
