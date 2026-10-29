import { useI18n } from "../../../i18n/useI18n";

import { shortcutLabel } from "./shortcuts";

import type { ProductionLabel, ProductionTemplate } from "./types";

export function LabelPicker({
  labels,
  template,
  value,
  onChange,
  readOnly,
}: {
  labels: readonly ProductionLabel[];
  template: ProductionTemplate;
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
}) {
  const { t } = useI18n();
  return (
    <label>
      {t("wbEditorLabel")}
      <select
        value={value}
        disabled={readOnly || labels.length === 0}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        onBlur={(event) => {
          onChange(event.target.value);
        }}
        onKeyDown={(event) => {
          // Label shortcuts work here too, instead of the list's type-ahead search.
          const picked = shortcutLabel(event.nativeEvent, labels, template);
          if (!picked) return;
          event.preventDefault();
          onChange(picked.id);
        }}
      >
        {labels.map((label) => (
          <option key={label.id} value={label.id}>
            {label.name}
          </option>
        ))}
      </select>
    </label>
  );
}
