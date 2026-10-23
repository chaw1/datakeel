import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import { formInputs, inputDefaults } from "./form";
import { inputLabel, workflowDescription, workflowName } from "./labels";

import type { Dataset } from "../../api/types";
import type { WorkflowDefinition, WorkflowStart } from "../../api/workflows";

export function WorkflowForm({
  definition,
  datasets,
  datasetId,
  busy,
  onStart,
}: {
  definition: WorkflowDefinition;
  datasets: Dataset[];
  datasetId: string;
  busy: boolean;
  onStart: (inputs: WorkflowStart["inputs"]) => void;
}) {
  const { t } = useI18n();
  const composing = useCompositionGuard();
  const [values, setValues] = useState(() =>
    inputDefaults(definition, datasetId),
  );
  const [error, setError] = useState("");
  const update = (name: string, value: string) => {
    setValues((current) => ({ ...current, [name]: value }));
  };
  return (
    <section
      className="card workflow-form-card"
      aria-label={t("workflowInputs")}
    >
      <h2>{workflowName(definition.id, t, definition.name)}</h2>
      <p className="muted">
        {workflowDescription(definition.id, t, definition.description)}
      </p>
      <form
        className="workflow-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (busy || composing()) return;
          try {
            setError("");
            onStart(formInputs(definition, values, t));
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : String(reason));
          }
        }}
      >
        {Object.entries(definition.inputs).map(([name, field]) => {
          const label = inputLabel(name, t);
          const fieldId = `workflow-input-${name}`;
          return (
            <div className="workflow-field" key={name}>
              <label htmlFor={fieldId}>
                {label}
                {field.required && (
                  <span className="muted small">
                    {" "}
                    · {t("workflowRequired")}
                  </span>
                )}
              </label>
              {name === "dataset_id" ? (
                <select
                  id={fieldId}
                  value={values[name]}
                  disabled={busy}
                  required={field.required}
                  onBlur={(event) => {
                    update(name, event.target.value);
                  }}
                  onChange={(event) => {
                    update(name, event.target.value);
                  }}
                >
                  <option value="">{t("workflowDatasetRequired")}</option>
                  {values[name] &&
                    !datasets.some(
                      (dataset) => dataset.id === values[name],
                    ) && <option value={values[name]}>{values[name]}</option>}
                  {datasets.map((dataset) => (
                    <option key={dataset.id} value={dataset.id}>
                      {dataset.name}
                    </option>
                  ))}
                </select>
              ) : ["object", "array"].includes(field.type) ? (
                <>
                  <textarea
                    id={fieldId}
                    rows={5}
                    value={values[name]}
                    required={field.required}
                    disabled={busy}
                    spellCheck={false}
                    onChange={(event) => {
                      update(name, event.target.value);
                    }}
                  />
                  <span className="muted small">{t("workflowJsonHint")}</span>
                </>
              ) : field.type === "boolean" ? (
                <input
                  id={fieldId}
                  type="checkbox"
                  checked={values[name] === "true"}
                  disabled={busy}
                  onChange={(event) => {
                    update(name, String(event.target.checked));
                  }}
                />
              ) : (
                <input
                  id={fieldId}
                  type={
                    ["integer", "number"].includes(field.type)
                      ? "number"
                      : "text"
                  }
                  step={field.type === "integer" ? 1 : "any"}
                  value={values[name]}
                  required={field.required}
                  disabled={busy}
                  onChange={(event) => {
                    update(name, event.target.value);
                  }}
                />
              )}
            </div>
          );
        })}
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          className="button primary"
          disabled={busy}
          onKeyDown={(event) => {
            if (composing(event.nativeEvent)) event.preventDefault();
          }}
        >
          {t(busy ? "workflowRunning" : "workflowStart")}
        </button>
      </form>
    </section>
  );
}
