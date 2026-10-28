import { useI18n } from "../../i18n/useI18n";

import type { CodeList } from "../../api/standards";

export function CodeEntriesEditor({
  entries,
  onChange,
}: {
  entries: CodeList["entries"];
  onChange: (entries: CodeList["entries"]) => void;
}) {
  const { t } = useI18n();
  function update(index: number, patch: Partial<CodeList["entries"][number]>) {
    onChange(
      entries.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)),
    );
  }
  function changeType(index: number, type: string) {
    update(index, {
      value:
        type === "number"
          ? 0
          : type === "boolean"
            ? false
            : type === "null"
              ? null
              : "",
    });
  }
  return (
    <div className="standards-page">
      {entries.map((entry, index) => {
        const type = entry.value === null ? "null" : typeof entry.value;
        return (
          <fieldset className="catalog-filter-editor" key={index}>
            <legend>
              {t("stdValue")} {index + 1}
            </legend>
            <div className="catalog-form-grid">
              <label>
                {t("stdValueType")}
                <select
                  value={type}
                  onBlur={(event) => {
                    if (type !== event.target.value)
                      changeType(index, event.target.value);
                  }}
                  onChange={(event) => {
                    changeType(index, event.target.value);
                  }}
                >
                  <option value="string">{t("stdTextValue")}</option>
                  <option value="number">{t("stdNumberValue")}</option>
                  <option value="boolean">{t("stdBooleanValue")}</option>
                  <option value="null">{t("stdNullValue")}</option>
                </select>
              </label>
              {type === "boolean" ? (
                <label>
                  {t("stdValue")}
                  <select
                    value={String(entry.value)}
                    onBlur={(event) => {
                      update(index, { value: event.target.value === "true" });
                    }}
                    onChange={(event) => {
                      update(index, { value: event.target.value === "true" });
                    }}
                  >
                    <option value="true">{t("yes")}</option>
                    <option value="false">{t("no")}</option>
                  </select>
                </label>
              ) : (
                type !== "null" && (
                  <label>
                    {t("stdValue")}
                    <input
                      required
                      type={type === "number" ? "number" : "text"}
                      step="any"
                      value={String(entry.value)}
                      onChange={(event) => {
                        update(index, {
                          value:
                            type === "number"
                              ? Number(event.target.value)
                              : event.target.value,
                        });
                      }}
                    />
                  </label>
                )
              )}
              {(
                [
                  ["label_zh", "stdNameZh"],
                  ["label_en", "stdNameEn"],
                ] as const
              ).map(([key, label]) => (
                <label key={key}>
                  {t(label)}
                  <input
                    required={key === "label_zh"}
                    value={entry[key]}
                    onChange={(event) => {
                      update(index, { [key]: event.target.value });
                    }}
                  />
                </label>
              ))}
            </div>
            <button
              type="button"
              className="text-button"
              onClick={() => {
                onChange(entries.filter((_, i) => i !== index));
              }}
            >
              {t("stdRemoveEntry")}
            </button>
          </fieldset>
        );
      })}
      <button
        type="button"
        className="button subtle"
        onClick={() => {
          onChange([...entries, { value: "", label_zh: "", label_en: "" }]);
        }}
      >
        {t("stdAddEntry")}
      </button>
    </div>
  );
}
