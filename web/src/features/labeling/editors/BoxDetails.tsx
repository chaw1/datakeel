import { useI18n } from "../../../i18n/useI18n";

import { CoordinateField } from "./CoordinateField";
import { EditorDetails } from "./EditorDetails";
import { ShapeProperties } from "./ShapeProperties";

import type { AnnotationBox, EditorProps } from "./types";

const FIELDS = {
  x1: "wbEditorX1",
  y1: "wbEditorY1",
  x2: "wbEditorX2",
  y2: "wbEditorY2",
} as const;

/** Hint, coordinates and attributes of the selected box, shown in the drawer. */
export function BoxDetails({
  current,
  width,
  height,
  readOnly,
  onUpdate,
}: EditorProps & {
  current: AnnotationBox | undefined;
  width: number;
  height: number;
  onUpdate: (box: AnnotationBox) => void;
}) {
  const { t } = useI18n();
  return (
    <EditorDetails label={t("wbEditorBox")}>
      <p className="muted">{t("wbEditorBoxHint")}</p>
      {current && (
        <>
          <div className="wb-coordinate-fields">
            {(["x1", "y1", "x2", "y2"] as const).map((field) => (
              <CoordinateField
                key={field}
                label={t(FIELDS[field])}
                value={current[field]}
                max={field.startsWith("x") ? width : height}
                readOnly={readOnly}
                onChange={(number) => {
                  const next = { ...current, [field]: number };
                  if (next.x2 > next.x1 && next.y2 > next.y1) onUpdate(next);
                }}
              />
            ))}
          </div>
          <ShapeProperties
            value={current.attributes}
            readOnly={readOnly}
            onChange={(attributes) => {
              onUpdate({ ...current, attributes });
            }}
          />
        </>
      )}
    </EditorDetails>
  );
}
