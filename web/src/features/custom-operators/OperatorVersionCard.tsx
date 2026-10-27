import { useState } from "react";

import { runCustomOperator } from "../../api/customOperators";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import { SourceReview } from "./SourceReview";

import type {
  CustomOperatorVersion,
  RunCustomOperatorRequest,
} from "../../api/customOperators";
import type { ActionRun, Dataset } from "../../api/types";

export function OperatorVersionCard({
  version,
  datasets,
  onQueued,
  blocked = false,
}: {
  version: CustomOperatorVersion;
  datasets: Dataset[];
  onQueued: (run: ActionRun) => void;
  blocked?: boolean;
}) {
  const { t, locale } = useI18n();
  const [chosenDataset, setChosenDataset] = useState("");
  const datasetId = chosenDataset || datasets[0]?.id || "";
  const [parameters, setParameters] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isComposing = useCompositionGuard();
  async function run() {
    if (busy || blocked || !datasetId || isComposing()) return;
    setError("");
    setBusy(true);
    try {
      let value: unknown;
      try {
        value = JSON.parse(parameters);
      } catch {
        throw new Error(t("customOperatorInvalidParams"));
      }
      if (value === null || typeof value !== "object" || Array.isArray(value))
        throw new Error(t("customOperatorInvalidParams"));
      const result = await runCustomOperator(version.code_hash, {
        dataset_id: datasetId,
        name: version.name,
        params: value as RunCustomOperatorRequest["params"],
      });
      onQueued(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="card custom-version" data-custom-version={version.id}>
      <header className="section-heading">
        <h3>{version.name}</h3>
        <span className="status-badge">{t("APPROVED")}</span>
      </header>
      <code className="custom-hash">{version.code_hash}</code>
      <p className="muted">
        {version.approved_by} · {date(version.approved_at, locale)}
      </p>
      <details>
        <summary>{t("customOperatorSource")}</summary>
        <SourceReview
          code={version.code}
          codeHash={version.code_hash}
          checks={version.static_checks}
        />
        <h4>{t("parameterSchema")}</h4>
        <pre className="custom-source">
          {JSON.stringify(version.parameter_schema, null, 2)}
        </pre>
        <h4>{t("outputSchema")}</h4>
        <pre className="custom-source">
          {JSON.stringify(version.metadata_schema, null, 2)}
        </pre>
      </details>
      <form
        className="custom-run-form"
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
      >
        <p className="muted">{t("customOperatorRunHint")}</p>
        {blocked && (
          <p className="error-text">{t("customOperatorContainerRequired")}</p>
        )}
        <label>
          {t("dataset")}
          <select
            aria-label={`${t("dataset")} · ${version.name}`}
            required
            disabled={busy || !datasets.length}
            value={datasetId}
            onBlur={(event) => {
              setChosenDataset(event.target.value);
            }}
            onChange={(event) => {
              setChosenDataset(event.target.value);
            }}
          >
            <option value="" disabled>
              {t("selectDataset")}
            </option>
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("customOperatorParams")}
          <textarea
            aria-label={`${t("customOperatorParams")} · ${version.name}`}
            spellCheck={false}
            value={parameters}
            disabled={busy}
            onChange={(event) => {
              setParameters(event.target.value);
            }}
          />
        </label>
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
        <button
          className="button primary"
          type="submit"
          disabled={busy || blocked || !datasetId}
          onKeyDown={(event) => {
            if (isComposing(event.nativeEvent)) event.preventDefault();
          }}
        >
          {t(busy ? "planWorking" : "customOperatorRun")}
        </button>
      </form>
    </article>
  );
}
