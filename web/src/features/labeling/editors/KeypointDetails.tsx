import { useI18n } from "../../../i18n/useI18n";

import { AttributeForm } from "./AttributeForm";
import { attributeFields } from "./attributes";
import { CoordinateField } from "./CoordinateField";
import { EditorDetails } from "./EditorDetails";
import { positioned } from "./keypoints";

import type {
  AnnotationKeypoint,
  AnnotationSkeleton,
  EditorProps,
  SkeletonDefinition,
} from "./types";

export function KeypointDetails({
  current,
  schema,
  pointIndex,
  width,
  height,
  template,
  advancedAttributes = true,
  readOnly,
  onPoint,
  onPointChange,
  onUpdate,
}: EditorProps & {
  current: AnnotationSkeleton | undefined;
  schema: SkeletonDefinition;
  pointIndex: number;
  width: number;
  height: number;
  onPoint: (index: number) => void;
  onPointChange: (point: AnnotationKeypoint) => void;
  onUpdate: (skeleton: AnnotationSkeleton) => void;
}) {
  const { t } = useI18n();
  const point = current?.points.at(pointIndex);
  function changeState(state: AnnotationKeypoint["state"]) {
    if (!point) return;
    onPointChange({
      ...point,
      state,
      ...(state === "missing"
        ? { x: null, y: null }
        : { x: point.x ?? 0, y: point.y ?? 0 }),
    });
  }
  const stateNames = {
    visible: t("wbKeypointState_visible"),
    occluded: t("wbKeypointState_occluded"),
    missing: t("wbKeypointState_missing"),
  };
  return (
    <EditorDetails label={t("wbEditorKeypoints")}>
      <p className="muted">{t("wbEditorKeypointHint")}</p>
      {current && (
        <>
          <fieldset className="wb-keypoint-list" disabled={readOnly}>
            <legend>{t("wbKeypointPoints")}</legend>
            {current.points.map((item, index) => (
              <button
                type="button"
                key={item.id}
                aria-pressed={index === pointIndex}
                onClick={() => {
                  onPoint(index);
                }}
              >
                {schema.points[index]?.name ?? item.id} ·{" "}
                {stateNames[item.state]}
              </button>
            ))}
          </fieldset>
          {point && (
            <>
              <label>
                {t("wbKeypointState")}
                <select
                  value={point.state}
                  disabled={readOnly}
                  onChange={(event) => {
                    changeState(
                      event.target.value as AnnotationKeypoint["state"],
                    );
                  }}
                  onBlur={(event) => {
                    changeState(
                      event.target.value as AnnotationKeypoint["state"],
                    );
                  }}
                >
                  {(["visible", "occluded", "missing"] as const).map(
                    (state) => (
                      <option key={state} value={state}>
                        {stateNames[state]}
                      </option>
                    ),
                  )}
                </select>
              </label>
              {positioned(point) && (
                <div className="wb-coordinate-fields">
                  <CoordinateField
                    label={t("wbEditorX")}
                    value={point.x}
                    max={width}
                    readOnly={readOnly}
                    onChange={(x) => {
                      onPointChange({ ...point, x });
                    }}
                  />
                  <CoordinateField
                    label={t("wbEditorY")}
                    value={point.y}
                    max={height}
                    readOnly={readOnly}
                    onChange={(y) => {
                      onPointChange({ ...point, y });
                    }}
                  />
                </div>
              )}
            </>
          )}
          <AttributeForm
            label={t("wbShapeAttributes")}
            fields={attributeFields(template, "object")}
            value={current.attributes}
            readOnly={readOnly}
            advanced={advancedAttributes}
            onChange={(attributes) => {
              onUpdate({ ...current, attributes });
            }}
          />
        </>
      )}
    </EditorDetails>
  );
}
