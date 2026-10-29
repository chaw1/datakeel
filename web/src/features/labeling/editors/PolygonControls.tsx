import { useI18n } from "../../../i18n/useI18n";

import { CoordinateField } from "./CoordinateField";
import { LabelPicker } from "./LabelPicker";
import { ShapeProperties } from "./ShapeProperties";

import type { AnnotationPolygon, Point, ProductionLabel } from "./types";

export function PolygonControls({
  labels,
  polygons,
  selected,
  category,
  pointIndex,
  cursor,
  draft,
  width,
  height,
  readOnly,
  onSelect,
  onLabel,
  onPoint,
  onCursor,
  onStart,
  onAddPoint,
  onFinish,
  onCancel,
  onDelete,
  onDeletePoint,
  onChange,
}: {
  labels: readonly ProductionLabel[];
  polygons: readonly AnnotationPolygon[];
  selected: number;
  category: string;
  pointIndex: number;
  cursor: Point;
  draft: readonly Point[] | null;
  width: number;
  height: number;
  readOnly?: boolean;
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
}) {
  const { t } = useI18n();
  const current = selected >= 0 ? polygons.at(selected) : undefined;
  const vertex = current?.points.at(pointIndex);
  return (
    <>
      <div className="wb-editor-toolbar">
        <LabelPicker
          labels={labels}
          value={current?.category ?? category}
          onChange={onLabel}
          readOnly={readOnly}
        />
        <button
          type="button"
          disabled={readOnly || !category}
          onClick={onStart}
        >
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
        <button
          type="button"
          disabled={readOnly || !current}
          onClick={onDelete}
        >
          {t("wbEditorDelete")}
        </button>
      </div>
      {draft !== null && (
        <div className="wb-editor-toolbar">
          <output>{t("wbEditorDrawingPoints", { count: draft.length })}</output>
          <CoordinateField
            label={t("wbEditorX")}
            value={cursor.x}
            max={width}
            readOnly={readOnly}
            onChange={(x) => {
              onCursor({ ...cursor, x });
            }}
          />
          <CoordinateField
            label={t("wbEditorY")}
            value={cursor.y}
            max={height}
            readOnly={readOnly}
            onChange={(y) => {
              onCursor({ ...cursor, y });
            }}
          />
          <button type="button" disabled={readOnly} onClick={onAddPoint}>
            {t("wbEditorAddPoint")}
          </button>
          <button
            type="button"
            disabled={readOnly || draft.length < 3}
            onClick={onFinish}
          >
            {t("wbEditorClosePolygon")}
          </button>
          <button type="button" onClick={onCancel}>
            {t("wbEditorCancelPolygon")}
          </button>
        </div>
      )}
      {current && vertex && (
        <>
          <div className="wb-coordinate-fields">
            <label>
              {t("wbEditorPoint")}
              <select
                value={pointIndex}
                onChange={(event) => {
                  onPoint(Number(event.target.value));
                }}
                onBlur={(event) => {
                  onPoint(Number(event.target.value));
                }}
              >
                {current.points.map((_, index) => (
                  <option key={index} value={index}>
                    {index + 1}
                  </option>
                ))}
              </select>
            </label>
            <CoordinateField
              label={t("wbEditorX")}
              value={vertex.x}
              max={width}
              readOnly={readOnly}
              onChange={(x) => {
                onChange({
                  ...current,
                  points: current.points.map((point, index) =>
                    index === pointIndex ? { ...point, x } : point,
                  ),
                });
              }}
            />
            <CoordinateField
              label={t("wbEditorY")}
              value={vertex.y}
              max={height}
              readOnly={readOnly}
              onChange={(y) => {
                onChange({
                  ...current,
                  points: current.points.map((point, index) =>
                    index === pointIndex ? { ...point, y } : point,
                  ),
                });
              }}
            />
            <button
              type="button"
              disabled={readOnly || current.points.length <= 3}
              onClick={onDeletePoint}
            >
              {t("wbEditorDeletePoint")}
            </button>
          </div>
          <ShapeProperties
            value={current.attributes}
            readOnly={readOnly}
            onChange={(attributes) => {
              onChange({ ...current, attributes });
            }}
          />
        </>
      )}
    </>
  );
}
