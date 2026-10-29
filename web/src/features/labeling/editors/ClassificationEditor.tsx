import { useId } from "react";

import { useI18n } from "../../../i18n/useI18n";

import { isTyping } from "./geometry";
import { KeyboardRegion } from "./KeyboardRegion";
import { ShapeProperties } from "./ShapeProperties";
import { labelShortcut, shortcutLabel } from "./shortcuts";

import type { EditorProps } from "./types";

export function ClassificationEditor({
  value,
  labels,
  template,
  onChange,
  readOnly,
}: EditorProps) {
  const { t } = useI18n();
  const group = useId();
  const multiple =
    template.component_config?.multiple === true ||
    template.component_config?.label_mode === "multi";
  const selected = value.labels ?? [];
  function toggle(category: string) {
    if (readOnly) return;
    const next = multiple
      ? selected.includes(category)
        ? selected.filter((label) => label !== category)
        : [...selected, category]
      : [category];
    onChange({ ...value, labels: next });
  }
  return (
    <KeyboardRegion
      label={t("wbEditorClassification")}
      onKeyDown={(event) => {
        if (
          readOnly ||
          isTyping(event.target) ||
          event.ctrlKey ||
          event.metaKey ||
          event.altKey
        )
          return;
        const label = shortcutLabel(event, labels, template);
        if (label) {
          event.preventDefault();
          toggle(label.id);
        }
      }}
    >
      <p className="muted">{t("wbEditorClassificationHint")}</p>
      {labels.length === 0 && <p role="status">{t("wbEditorNoLabels")}</p>}
      <fieldset className="wb-classification-labels" disabled={readOnly}>
        <legend>{t(multiple ? "wbEditorMulti" : "wbEditorSingle")}</legend>
        {labels.map((label, index) => (
          <label key={label.id}>
            <input
              type={multiple ? "checkbox" : "radio"}
              name={group}
              value={label.id}
              checked={selected.includes(label.id)}
              onChange={() => {
                toggle(label.id);
              }}
            />
            <span>{label.name}</span>
            <kbd>{labelShortcut(label, index, template)}</kbd>
          </label>
        ))}
      </fieldset>
      <button
        type="button"
        disabled={readOnly || selected.length === 0}
        onClick={() => {
          onChange({ ...value, labels: [] });
        }}
      >
        {t("wbEditorClear")}
      </button>
      <ShapeProperties
        value={value.attributes}
        readOnly={readOnly}
        onChange={(attributes) => {
          onChange({ ...value, attributes });
        }}
      />
    </KeyboardRegion>
  );
}
