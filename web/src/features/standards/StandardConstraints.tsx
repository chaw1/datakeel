import { useI18n } from "../../i18n/useI18n";

import type { FieldStandard } from "../../api/standards";

export function StandardConstraints({
  draft,
  onChange,
}: {
  draft: FieldStandard;
  onChange: (draft: FieldStandard) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="catalog-form-grid">
      {(
        [
          ["length", "stdLength"],
          ["precision", "stdPrecision"],
          ["scale", "stdScale"],
          ["minimum", "stdMinimum"],
          ["maximum", "stdMaximum"],
        ] as const
      ).map(([key, label]) => (
        <label key={key}>
          {t(label)}
          <input
            type="number"
            step={key === "minimum" || key === "maximum" ? "any" : "1"}
            value={draft[key] ?? ""}
            onChange={(event) => {
              onChange({
                ...draft,
                [key]:
                  event.target.value === "" ? null : Number(event.target.value),
              });
            }}
          />
        </label>
      ))}
      {(
        [
          ["code_list", "stdCodes"],
          ["pattern", "stdPattern"],
          ["unit", "stdUnit"],
        ] as const
      ).map(([key, label]) => (
        <label key={key}>
          {t(label)}
          <input
            value={draft[key] ?? ""}
            onChange={(event) => {
              onChange({ ...draft, [key]: event.target.value || null });
            }}
          />
        </label>
      ))}
      <label>
        {t("stdRequired")}
        <select
          value={draft.required ? "yes" : "no"}
          onBlur={(event) => {
            onChange({ ...draft, required: event.target.value === "yes" });
          }}
          onChange={(event) => {
            onChange({ ...draft, required: event.target.value === "yes" });
          }}
        >
          <option value="yes">{t("yes")}</option>
          <option value="no">{t("no")}</option>
        </select>
      </label>
    </div>
  );
}
