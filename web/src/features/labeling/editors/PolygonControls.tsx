import { useI18n } from "../../../i18n/useI18n";

import { LabelPicker } from "./LabelPicker";

import type {
  AnnotationPolygon,
  Point,
  ProductionLabel,
  ProductionTemplate,
} from "./types";

export interface PolygonControlProps {
  labels: readonly ProductionLabel[];
  template: ProductionTemplate;
  polygons: readonly AnnotationPolygon[];
  selected: number;
  category: string;
  pointIndex: number;
  cursor: Point;
  draft: readonly Point[] | null;
  width: number;
  height: number;
  readOnly?: boolean;
  advancedAttributes?: boolean;
  /** What the arrow keys change right now; R switches it. */
  keyMode?: string;
  onSelect: (index: number) => void;
  onLabel: (label: string) => void;
  onPoint: (index: number) => void;
  onCursor: (point: Point) => void;
  onStart: () => void;
  onAddPoint: () => void;
  onFinish: () => void;
  onCancel: () => void;
  onDelete: () => void;
  onDeletePoint: () => void;
  onChange: (polygon: AnnotationPolygon) => void;
}

/** Stable controls above the canvas: drawing must never change the canvas position. */
export function PolygonToolbar({
  labels,
  template,
  polygons,
  selected,
  category,
  readOnly,
  keyMode,
  onSelect,
  onLabel,
  onStart,
  onDelete,
}: PolygonControlProps) {
  const { t } = useI18n();
  const current = selected >= 0 ? polygons.at(selected) : undefined;
  return (
    <div className="wb-editor-toolbar">
      <LabelPicker
        labels={labels}
        template={template}
        value={current?.category ?? category}
        onChange={onLabel}
        readOnly={readOnly}
      />
      <button type="button" disabled={readOnly || !category} onClick={onStart}>
        {t("wbEditorStartPolygon")}
      </button>
      <label>
        {t("wbEditorSelected")}
        <select
          value={current ? selected : -1}
          onChange={(event) => {
            onSelect(Number(event.target.value));
          }}
          onBlur={(event) => {
            onSelect(Number(event.target.value));
          }}
        >
          <option value={-1}>{t("wbEditorNone")}</option>
          {polygons.map((polygon, index) => (
            <option key={index} value={index}>
              {t("wbEditorAnnotationName", {
                label:
                  labels.find((item) => item.id === polygon.category)?.name ??
                  polygon.category,
                index: index + 1,
              })}
            </option>
          ))}
        </select>
      </label>
      <button type="button" disabled={readOnly || !current} onClick={onDelete}>
        {t("wbEditorDelete")}
      </button>
      {keyMode && (
        <p className="muted wb-key-mode" aria-live="polite">
          {keyMode}
        </p>
      )}
    </div>
  );
}
