import { useI18n } from "../../../i18n/useI18n";

import { AttributeForm } from "./AttributeForm";
import { attributeFields } from "./attributes";
import { EditorDetails } from "./EditorDetails";
import { formatTime } from "./segments";

import type { AnnotationSegment, EditorProps } from "./types";

export function SegmentDetails({
  value,
  labels,
  template,
  duration,
  selected,
  readOnly,
  advancedAttributes = true,
  onSelect,
  onUpdate,
}: EditorProps & {
  duration: number;
  selected: number;
  onSelect: (index: number) => void;
  onUpdate: (segment: AnnotationSegment) => void;
}) {
  const { t } = useI18n();
  const segments = value.segments ?? [];
  const current = segments.at(selected);
  return (
    <EditorDetails label={t("wbEditorSegment")}>
      <label>
        {t("wbSegmentList")}
        <select
          value={selected}
          onBlur={() => undefined}
          onChange={(event) => {
            onSelect(Number(event.target.value));
          }}
        >
          <option value={-1}>{t("wbEditorNone")}</option>
          {segments.map((segment, index) => (
            <option key={index} value={index}>
              {index + 1} · {segment.category} · {formatTime(segment.start_ms)}–
              {formatTime(segment.end_ms)}
            </option>
          ))}
        </select>
      </label>
      {current && (
        <>
          <label>
            {t("wbEditorLabel")}
            <select
              value={current.category}
              disabled={readOnly}
              onBlur={() => undefined}
              onChange={(event) => {
                onUpdate({ ...current, category: event.target.value });
              }}
            >
              {labels.map((label) => (
                <option key={label.id} value={label.id}>
                  {label.name}
                </option>
              ))}
            </select>
          </label>
          <div className="wb-coordinate-fields">
            {(["start_ms", "end_ms"] as const).map((field) => (
              <label key={field}>
                {t(field === "start_ms" ? "wbSegmentStart" : "wbSegmentEnd")}
                <input
                  type="number"
                  min={field === "end_ms" ? 1 : 0}
                  max={duration}
                  step={1}
                  value={current[field]}
                  readOnly={readOnly}
                  onChange={(event) => {
                    const milliseconds = event.target.valueAsNumber;
                    if (!Number.isInteger(milliseconds)) return;
                    const next = { ...current, [field]: milliseconds };
                    if (
                      next.start_ms >= 0 &&
                      next.start_ms < next.end_ms &&
                      next.end_ms <= duration
                    )
                      onUpdate(next);
                  }}
                />
              </label>
            ))}
          </div>
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
