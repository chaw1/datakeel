import { useI18n } from "../../../i18n/useI18n";

import { AttributeForm } from "./AttributeForm";
import { attributeFields } from "./attributes";
import { CoordinateField } from "./CoordinateField";

import type { PolygonControlProps } from "./PolygonControls";

/** Draft and vertex fields below the canvas, so their appearance never moves it. */
export function PolygonDetails({
  template,
  advancedAttributes = true,
  polygons,
  selected,
  pointIndex,
  cursor,
  draft,
  width,
  height,
  readOnly,
  onPoint,
  onCursor,
  onAddPoint,
  onFinish,
  onCancel,
  onDeletePoint,
  onChange,
}: PolygonControlProps) {
  const { t } = useI18n();
  const current = selected >= 0 ? polygons.at(selected) : undefined;
  const vertex = current?.points.at(pointIndex);
  return (
    <>
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
          <AttributeForm
            label={t("wbEditorProperties")}
            fields={attributeFields(template, "object")}
            value={current.attributes}
            readOnly={readOnly}
            advanced={advancedAttributes}
            onChange={(attributes) => {
              onChange({ ...current, attributes });
            }}
          />
        </>
      )}
    </>
  );
}
