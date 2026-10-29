import { useI18n } from "../../../i18n/useI18n";

import type { ProductionLabel } from "./types";

export function LabelPicker({
  labels,
  value,
  onChange,
  readOnly,
}: {
  labels: readonly ProductionLabel[];
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
