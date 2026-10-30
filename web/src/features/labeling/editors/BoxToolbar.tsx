import { useI18n } from "../../../i18n/useI18n";

import { LabelPicker } from "./LabelPicker";

import type {
  AnnotationBox,
  ProductionLabel,
  ProductionTemplate,
} from "./types";

/** Box tools in one row above the canvas. */
export function BoxToolbar({
  labels,
  template,
  boxes,
  selected,
  category,
  readOnly,
  onLabel,
  onSelect,
  onAdd,
  onCopy,
  onDelete,
  keyMode,
}: {
  labels: readonly ProductionLabel[];
  template: ProductionTemplate;
  boxes: readonly AnnotationBox[];
  selected: number;
  category: string;
  readOnly?: boolean;
  onLabel: (label: string) => void;
  onSelect: (index: number) => void;
  onAdd: () => void;
  onCopy: () => void;
  onDelete: () => void;
  /** What the arrow keys change right now; R switches it. */
  keyMode?: string;
}) {
  const { t } = useI18n();
  return (
    <>
      <LabelPicker
        labels={labels}
        template={template}
        value={category}
        readOnly={readOnly}
        onChange={onLabel}
      />
      <button type="button" disabled={readOnly || !category} onClick={onAdd}>
        {t("wbEditorAddBox")}
      </button>
      <label>
        {t("wbEditorSelected")}
        <select
          value={selected}
          onChange={(event) => {
            onSelect(Number(event.target.value));
          }}
          onBlur={(event) => {
            onSelect(Number(event.target.value));
          }}
        >
          <option value={-1}>{t("wbEditorNone")}</option>
          {boxes.map((box, index) => (
            <option key={index} value={index}>
              {t("wbEditorAnnotationName", {
                label:
                  labels.find((item) => item.id === box.category)?.name ??
                  box.category,
                index: index + 1,
              })}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        disabled={readOnly || selected < 0}
        onClick={onCopy}
      >
        {t("wbEditorCopy")}
      </button>
      <button
        type="button"
        disabled={readOnly || selected < 0}
        onClick={onDelete}
      >
        {t("wbEditorDelete")}
      </button>
      {keyMode && (
        <p className="muted wb-key-mode" aria-live="polite">
          {keyMode}
        </p>
      )}
    </>
  );
}
