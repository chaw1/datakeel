import { useI18n } from "../../../i18n/useI18n";

import { fieldName, optionName } from "./attributes";

import type { AttributeField } from "./attributes";

/** One typed attribute control; `undefined` clears an optional value. */
export function AttributeInput({
  field,
  value,
  invalid,
  onChange,
}: {
  field: AttributeField;
  value: unknown;
  invalid: boolean;
  onChange: (value: unknown) => void;
}) {
  const { t, locale } = useI18n();
  const name = fieldName(field, locale);
  const option = (choice: string) => optionName(field, choice, locale);
  const marker = field.required ? ` (${t("wbAttributeRequired")})` : "";
  if (field.type === "boolean")
    return (
      <label className="wb-attribute-check">
        <input
          type="checkbox"
          checked={value === true}
          onChange={(event) => {
            onChange(event.target.checked);
          }}
        />
        {name}
        {marker}
      </label>
    );
  if (field.type === "multi_enum") {
    const selected = Array.isArray(value)
      ? value.filter((entry): entry is string => typeof entry === "string")
      : [];
    return (
      <fieldset className="wb-attribute-choices" aria-invalid={invalid}>
        <legend>
          {name}
          {marker}
        </legend>
        {field.options.map((item) => (
          <label key={item.value} className="wb-attribute-check">
            <input
              type="checkbox"
              checked={selected.includes(item.value)}
              onChange={(event) => {
                const next = event.target.checked
                  ? [...selected, item.value]
                  : selected.filter((entry) => entry !== item.value);
                onChange(next.length || field.required ? next : undefined);
              }}
            />
            {option(item.value)}
          </label>
        ))}
      </fieldset>
    );
  }
  return (
    <label>
      {name}
      {marker}
      {field.type === "enum" ? (
        <select
          value={typeof value === "string" ? value : ""}
          aria-required={field.required}
          aria-invalid={invalid}
          onBlur={(event) => {
            if (event.target.value !== (value ?? ""))
              onChange(event.target.value || undefined);
          }}
          onChange={(event) => {
            onChange(event.target.value || undefined);
          }}
        >
          <option value="">{t("wbAttributeUnset")}</option>
          {field.options.map((item) => (
            <option key={item.value} value={item.value}>
              {option(item.value)}
            </option>
          ))}
        </select>
      ) : field.type === "number" ? (
        <input
          type="number"
          step="any"
          min={field.minimum ?? undefined}
          max={field.maximum ?? undefined}
          value={typeof value === "number" ? value : ""}
          aria-required={field.required}
          aria-invalid={invalid}
          onChange={(event) => {
            const number = event.target.valueAsNumber;
            if (event.target.value === "") onChange(undefined);
            else if (Number.isFinite(number)) onChange(number);
          }}
        />
      ) : (
        <input
          type="text"
          maxLength={field.max_length}
          value={typeof value === "string" ? value : ""}
          aria-required={field.required}
          aria-invalid={invalid}
          onChange={(event) => {
            onChange(event.target.value || undefined);
          }}
        />
      )}
    </label>
  );
}
