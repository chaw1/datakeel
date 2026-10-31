import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { actionDetails, mutateProduction } from "./actions";

import type {
  ProjectWorkbench,
  ProductionTemplate,
} from "../../api/production";

const components = ["box", "polygon", "classification", "text_span"] as const;
const componentNames = {
  box: "wbEditorBox",
  polygon: "wbEditorPolygon",
  classification: "wbEditorClassification",
  text_span: "wbEditorSpan",
} as const;

function shortcutMap(
  source: string,
  errorText: string,
): Record<string, string> {
  let value: unknown;
  try {
    value = JSON.parse(source);
  } catch {
    throw new Error(errorText);
  }
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    !Object.values(value).every((item) => typeof item === "string")
  )
    throw new Error(errorText);
  return value as Record<string, string>;
}

function attributeList(source: string, errorText: string) {
  let value: unknown;
  try {
    value = JSON.parse(source || "[]");
  } catch {
    throw new Error(errorText);
  }
  if (!Array.isArray(value)) throw new Error(errorText);
  return value as ProductionTemplate["attributes"];
}

export function TemplateEditor({
  project,
  onChanged,
}: {
  project: ProjectWorkbench;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  // Edits build the template's next version from its newest revision; this project stays on
  // its locked version until an upgrade is signed in the cockpit.
  const template = project.latest_template ?? project.template;
  const [type, setType] = useState<ProductionTemplate["annotation_type"]>(
    template?.annotation_type ?? "box",
  );
  const [selected, setSelected] = useState<string[]>(
    Array.isArray(template?.component_config?.components)
      ? template.component_config.components.filter(
          (value): value is string => typeof value === "string",
        )
      : [template?.annotation_type ?? "box"],
  );
  const [guide, setGuide] = useState(
    typeof template?.component_config?.guidelines === "string"
      ? template.component_config.guidelines
      : "",
  );
  const [shortcuts, setShortcuts] = useState(
    JSON.stringify(template?.component_config?.shortcuts ?? {}, null, 2),
  );
  const [mode, setMode] = useState(
    template?.component_config?.label_mode === "multi" ? "multi" : "single",
  );
  const [attributes, setAttributes] = useState(
    JSON.stringify(template?.attributes ?? [], null, 2),
  );
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  async function apply() {
    if (!template || busy) return;
    setBusy(true);
    setError("");
    setSaved(null);
    try {
      const run = await mutateProduction("create_label_set", {
        target: "template",
        operation: "update",
        template: {
          ...template,
          annotation_type: type,
          attributes: attributeList(attributes, t("wbInvalidAttributes")),
          component_config: {
            ...template.component_config,
            components: selected.length ? selected : [type],
            guidelines: guide,
            label_mode: mode,
            shortcuts: shortcutMap(shortcuts, t("wbInvalidShortcuts")),
          },
        },
      });
      const details = actionDetails(run);
      setSaved(
        details &&
          typeof details === "object" &&
          "revision" in details &&
          typeof details.revision === "number"
          ? details.revision
          : template.revision + 1,
      );
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("wbError"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="card wb-template">
      <summary>{t("wbTemplate")}</summary>
      {!template ? (
        <p>{t("wbTemplateMissing")}</p>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void apply();
          }}
        >
          <p>
            {template.name} ·{" "}
            {t("wbTemplateVersion", { version: template.revision })}
          </p>
          <label>
            {t("wbTemplateType")}
            <select
              value={type}
              onBlur={() => undefined}
              onChange={(event) => {
                setType(
                  event.target.value as ProductionTemplate["annotation_type"],
                );
              }}
            >
              {components.map((item) => (
                <option key={item} value={item}>
                  {t(componentNames[item])}
                </option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>{t("wbTemplateComponents")}</legend>
            {components.map((item) => (
              <label key={item}>
                <input
                  type="checkbox"
                  checked={selected.includes(item)}
                  onChange={(event) => {
                    setSelected(
                      event.target.checked
                        ? [...selected, item]
                        : selected.filter((value) => value !== item),
                    );
                  }}
                />
                {t(componentNames[item])}
              </label>
            ))}
          </fieldset>
          <label>
            {t("wbTemplateMode")}
            <select
              value={mode}
              onBlur={() => undefined}
              onChange={(event) => {
                setMode(event.target.value);
              }}
            >
              <option value="single">{t("wbSingle")}</option>
              <option value="multi">{t("wbMulti")}</option>
            </select>
          </label>
          <label>
            {t("wbTemplateGuide")}
            <textarea
              value={guide}
              onChange={(event) => {
                setGuide(event.target.value);
              }}
            />
          </label>
          <label>
            {t("wbTemplateShortcuts")}
            <textarea
              value={shortcuts}
              onChange={(event) => {
                setShortcuts(event.target.value);
              }}
            />
          </label>
          <label>
            {t("wbTemplateAttributes")}
            <textarea
              value={attributes}
              onChange={(event) => {
                setAttributes(event.target.value);
              }}
            />
          </label>
          <button type="submit" disabled={busy}>
            {t("wbApplyTemplate")}
          </button>
        </form>
      )}
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      {saved !== null && (
        <p role="status">{t("wbTemplateSavedVersion", { version: saved })}</p>
      )}
    </details>
  );
}
