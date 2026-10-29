import { useState } from "react";
import { Rect } from "react-konva";

import { useI18n } from "../../../i18n/useI18n";

import { BoxShape } from "./BoxShape";
import { CoordinateField } from "./CoordinateField";
import {
  arrowDelta,
  boxFromPoints,
  isTyping,
  moveBox,
  resizeBox,
} from "./geometry";
import { ImageCanvas } from "./ImageCanvas";
import { KeyboardRegion } from "./KeyboardRegion";
import { LabelPicker } from "./LabelPicker";
import { ShapeProperties } from "./ShapeProperties";
import { shortcutLabel } from "./shortcuts";
import { useCanvasTokens } from "./useCanvasTokens";

import type { AnnotationBox, EditorProps, Point } from "./types";

export function BboxEditor(props: EditorProps) {
  const { value, labels, onChange, readOnly } = props;
  const { t } = useI18n();
  const tokens = useCanvasTokens();
  const [label, setLabel] = useState(labels[0]?.id ?? "");
  const [selected, setSelected] = useState(-1);
  const [draft, setDraft] = useState<{ start: Point; end: Point } | null>(null);
  const boxes = value.boxes ?? [];
  const current = selected >= 0 ? boxes.at(selected) : undefined;
  const category =
    current?.category ??
    (labels.some((item) => item.id === label) ? label : (labels[0]?.id ?? ""));
  const width = value.image_width ?? 2000,
    height = value.image_height ?? 1500;
  function update(box: AnnotationBox) {
    if (!readOnly)
      onChange({
        ...value,
        boxes: boxes.map((item, index) => (index === selected ? box : item)),
      });
  }
  function append(box: AnnotationBox) {
    if (readOnly || !category) return;
    onChange({
      ...value,
      image_width: width,
      image_height: height,
      boxes: [...boxes, box],
    });
    setSelected(boxes.length);
  }
  function add() {
    append({
      category,
      x1: width * 0.1,
      y1: height * 0.1,
      x2: width * 0.3,
      y2: height * 0.3,
      attributes: {},
    });
  }
  function remove() {
    if (readOnly || !current) return;
    onChange({
      ...value,
      boxes: boxes.filter((_, index) => index !== selected),
    });
    setSelected(Math.min(selected, boxes.length - 2));
  }
  function copy() {
    if (current) append(moveBox(current, 10, 10, width, height));
  }
  const preview = draft
    ? boxFromPoints(draft.start, draft.end, category)
    : null;
  return (
    <KeyboardRegion
      label={t("wbEditorBox")}
      onKeyDown={(event) => {
        if (readOnly || isTyping(event.target) || event.altKey) return;
        const delta = arrowDelta(event.key);
        if (
          (event.ctrlKey || event.metaKey) &&
          event.key.toLowerCase() === "d"
        ) {
          event.preventDefault();
          copy();
        } else if (event.ctrlKey || event.metaKey) return;
        else if (event.key.toLowerCase() === "b") {
          event.preventDefault();
          add();
        } else if (event.key === "Delete" || event.key === "Backspace") {
          event.preventDefault();
          remove();
        } else if (delta && current) {
          event.preventDefault();
          update(
            event.shiftKey
              ? resizeBox(current, delta.x, delta.y, width, height)
              : moveBox(current, delta.x, delta.y, width, height),
          );
        } else {
          const picked = shortcutLabel(event, labels, props.template);
          if (picked) {
            event.preventDefault();
            setLabel(picked.id);
            if (current) update({ ...current, category: picked.id });
          }
        }
      }}
    >
      <p className="muted">{t("wbEditorBoxHint")}</p>
      {labels.length === 0 && <p role="status">{t("wbEditorNoLabels")}</p>}
      <div className="wb-editor-toolbar">
        <LabelPicker
          labels={labels}
          value={current?.category ?? category}
          readOnly={readOnly}
          onChange={(next) => {
            setLabel(next);
            if (current) update({ ...current, category: next });
          }}
        />
        <button type="button" disabled={readOnly || !category} onClick={add}>
          {t("wbEditorAddBox")}
        </button>
        <label>
          {t("wbEditorSelected")}
          <select
            value={current ? selected : -1}
            onChange={(event) => {
              setSelected(Number(event.target.value));
            }}
            onBlur={(event) => {
              setSelected(Number(event.target.value));
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
        <button type="button" disabled={readOnly || !current} onClick={copy}>
          {t("wbEditorCopy")}
        </button>
        <button type="button" disabled={readOnly || !current} onClick={remove}>
          {t("wbEditorDelete")}
        </button>
      </div>
      <ImageCanvas
        width={width}
        height={height}
        mediaUrl={props.mediaUrl}
        thumbnailUrl={props.thumbnailUrl}
        onStart={(point) => {
          if (!readOnly && category) setDraft({ start: point, end: point });
        }}
        onMove={(point) => {
          if (draft) setDraft({ ...draft, end: point });
        }}
        onFinish={(point) => {
          if (!draft) return;
          const box = boxFromPoints(draft.start, point, category);
          if (box.x2 - box.x1 >= 1 && box.y2 - box.y1 >= 1) append(box);
          setDraft(null);
        }}
      >
        {boxes.map((box, index) => (
          <BoxShape
            key={index}
            value={box}
            selected={index === selected}
            color={tokens.accent}
            width={width}
            height={height}
            readOnly={readOnly}
            onSelect={() => {
              setSelected(index);
            }}
            onChange={(next) => {
              if (!readOnly)
                onChange({
                  ...value,
                  boxes: boxes.map((item, i) => (i === index ? next : item)),
                });
            }}
          />
        ))}
        {preview && (
          <Rect
            x={preview.x1}
            y={preview.y1}
            width={preview.x2 - preview.x1}
            height={preview.y2 - preview.y1}
            stroke={tokens.accent}
            strokeWidth={2}
            strokeScaleEnabled={false}
            listening={false}
            dash={[4, 4]}
          />
        )}
      </ImageCanvas>
      {current && (
        <>
          <div className="wb-coordinate-fields">
            {(["x1", "y1", "x2", "y2"] as const).map((field) => (
              <CoordinateField
                key={field}
                label={t(
                  (
                    {
                      x1: "wbEditorX1",
                      y1: "wbEditorY1",
                      x2: "wbEditorX2",
                      y2: "wbEditorY2",
                    } as const
                  )[field],
                )}
                value={current[field]}
                max={field.startsWith("x") ? width : height}
                readOnly={readOnly}
                onChange={(number) => {
                  const next = { ...current, [field]: number };
                  if (next.x2 > next.x1 && next.y2 > next.y1) update(next);
                }}
              />
            ))}
          </div>
          <ShapeProperties
            value={current.attributes}
            readOnly={readOnly}
            onChange={(attributes) => {
              update({ ...current, attributes });
            }}
          />
        </>
      )}
    </KeyboardRegion>
  );
}
