import { useI18n } from "../../../i18n/useI18n";

import { AttributeInput } from "./AttributeInput";
import { valueFits } from "./attributes";
import { ShapeProperties } from "./ShapeProperties";

import type { AttributeField } from "./attributes";
import type { Attributes } from "./types";

/**
 * Render template attribute fields as native, keyboard-reachable controls.
 * Raw JSON stays behind the project manager's "Advanced" disclosure.
 */
export function AttributeForm({
  fields,
  value,
  onChange,
  readOnly,
  advanced,
  label,
}: {
  fields: readonly AttributeField[];
  value: Attributes | undefined;
  onChange: (value: Attributes) => void;
  readOnly?: boolean;
  advanced: boolean;
  label: string;
}) {
  const { t } = useI18n();
  const current = value ?? {};
  if (!fields.length && !advanced) return null;
  return (
    <div className="wb-attributes">
      {fields.length > 0 && (
        <fieldset className="wb-attribute-fields" disabled={readOnly}>
          <legend>{label}</legend>
          {fields.map((field) => {
            const fieldValue = current[field.key];
            return (
              <AttributeInput
                key={`${field.target}:${field.key}`}
                field={field}
                value={fieldValue}
                invalid={fieldValue != null && !valueFits(field, fieldValue)}
                onChange={(next) => {
                  const updated = Object.fromEntries(
                    Object.entries(current).filter(
                      ([key]) => key !== field.key,
                    ),
                  );
                  onChange(
                    next === undefined
                      ? updated
                      : { ...updated, [field.key]: next },
                  );
                }}
              />
            );
          })}
        </fieldset>
      )}
      {advanced && (
        <details className="wb-attributes-advanced">
          <summary>{t("wbAttributesAdvanced")}</summary>
          <ShapeProperties
            value={current}
            readOnly={readOnly}
            onChange={onChange}
          />
        </details>
      )}
    </div>
  );
}
