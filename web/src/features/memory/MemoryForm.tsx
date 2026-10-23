import { useState } from "react";

import { createMemory } from "../../api/memory";
import { useI18n } from "../../i18n/useI18n";

import type { Dataset } from "../../api/types";

export function MemoryForm({
  datasets,
  onSaved,
}: {
  datasets: Dataset[];
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [content, setContent] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save() {
    if (!content.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await createMemory({
        content: content.trim(),
        dataset_id: datasetId || null,
        idempotency_key: crypto.randomUUID(),
      });
      setContent("");
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="card memory-form"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <h2>{t("memoryAdd")}</h2>
      <label htmlFor="memory-content">{t("memoryContent")}</label>
      <textarea
        id="memory-content"
        required
        value={content}
        disabled={busy}
        onChange={(event) => {
          setContent(event.target.value);
        }}
      />
      <label htmlFor="memory-scope">{t("memoryScope")}</label>
      <select
        id="memory-scope"
        onBlur={(event) => {
          setDatasetId(event.target.value);
        }}
        value={datasetId}
        disabled={busy}
        onChange={(event) => {
          setDatasetId(event.target.value);
        }}
      >
        <option value="">{t("memoryGlobal")}</option>
        {datasets.map((dataset) => (
          <option key={dataset.id} value={dataset.id}>
            {dataset.name}
          </option>
        ))}
      </select>
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      <button
        className="button primary"
        type="submit"
        disabled={busy || !content.trim()}
      >
        {t(busy ? "memoryAdding" : "memoryAdd")}
      </button>
    </form>
  );
}
