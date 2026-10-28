import { useState } from "react";

import { importAnnotationBatch } from "../../api/annotation";
import { useI18n } from "../../i18n/useI18n";

import type { AnnotationBatch, AnnotationReport } from "../../api/annotation";

export function AnnotationImport({
  datasetId,
  versionId,
  batches,
  onChanged,
}: {
  datasetId: string;
  versionId: string;
  batches: AnnotationReport[];
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [baseline, setBaseline] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit() {
    if (!file || busy || !versionId) return;
    setBusy(true);
    setError("");
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (
        !parsed ||
        typeof parsed !== "object" ||
        !("annotations" in parsed) ||
        !Array.isArray(parsed.annotations)
      )
        throw new Error(t("annotationImportHint"));
      await importAnnotationBatch(datasetId, {
        version_id: versionId,
        name: name || file.name,
        batch: parsed as AnnotationBatch,
        idempotency_key: crypto.randomUUID(),
        ...(baseline ? { rework_of: baseline } : {}),
      });
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="card">
      <summary>{t("annotationImport")}</summary>
      <p>{t("annotationImportHint")}</p>
      <form
        className="annotation-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label>
          {t("annotationName")}
          <input
            value={name}
            maxLength={200}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </label>
        <label>
          {t("annotationFile")}
          <input
            type="file"
            accept="application/json,.json"
            required
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
            }}
          />
        </label>
        <label>
          {t("annotationReworkBaseline")}
          <select
            value={baseline}
            onChange={(event) => {
              setBaseline(event.target.value);
            }}
            onBlur={(event) => {
              setBaseline(event.target.value);
            }}
          >
            <option value="">{t("annotationNoBaseline")}</option>
            {batches.map((batch) => (
              <option key={batch.id} value={batch.id}>
                {batch.name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="button primary"
          disabled={busy || !file || !versionId}
        >
          {t(busy ? "annotationBusy" : "annotationImport")}
        </button>
      </form>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
    </details>
  );
}
