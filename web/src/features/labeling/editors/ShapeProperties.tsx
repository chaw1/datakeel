import { useState } from "react";

import { useI18n } from "../../../i18n/useI18n";

import { parseAttributes } from "./geometry";

import type { Attributes } from "./types";

export function ShapeProperties({
  value,
  onChange,
  readOnly,
}: {
  value?: Attributes;
  onChange: (value: Attributes) => void;
  readOnly?: boolean;
}) {
  const { t } = useI18n();
  const [error, setError] = useState(false);
  return (
    <form
      className="wb-properties"
      onSubmit={(event) => {
        event.preventDefault();
        const source = new FormData(event.currentTarget).get("attributes");
        const attributes =
          typeof source === "string" ? parseAttributes(source) : null;
        setError(attributes === null);
        if (attributes !== null) onChange(attributes);
      }}
    >
      <label>
        {t("wbEditorProperties")}
        <textarea
          key={JSON.stringify(value)}
          name="attributes"
          defaultValue={JSON.stringify(value ?? {}, null, 2)}
          readOnly={readOnly}
          rows={3}
          spellCheck={false}
        />
      </label>
      {error && <p role="alert">{t("wbEditorInvalidProperties")}</p>}
      <button type="submit" disabled={readOnly}>
        {t("wbEditorApplyProperties")}
      </button>
    </form>
  );
}
