import { useState } from "react";
import { Rect } from "react-konva";

import { useI18n } from "../../../i18n/useI18n";

import { attributeFields, withDefaults } from "./attributes";
import { BoxDetails } from "./BoxDetails";
import { BoxShape } from "./BoxShape";
import { BoxToolbar } from "./BoxToolbar";
import { boxChipAnchor } from "./chipLayout";
import {
  arrowDelta,
  boxFromPoints,
  isTyping,
  keyStep,
  moveBox,
  resizeBox,
  resizeBoxStart,
} from "./geometry";
import { ImageCanvas } from "./ImageCanvas";
import { KeyboardRegion } from "./KeyboardRegion";
import { labelStyle } from "./labelColors";
import { ShapeLabels } from "./ShapeLabels";
import { shortcutLabel } from "./shortcuts";
import { useCanvasTokens } from "./useCanvasTokens";
import { useLocate } from "./useLocate";

import type { AnnotationBox, EditorProps, Point } from "./types";

export function BboxEditor(props: EditorProps) {
  const { value, labels, onChange, readOnly } = props;
  const { t } = useI18n();
  const tokens = useCanvasTokens();
  const [label, setLabel] = useState(labels[0]?.id ?? "");
  const [selected, setSelected] = useState(-1);
  // R cycles what the arrows change: the whole box, its bottom-right, then its top-left edges.
  const [edge, setEdge] = useState<"move" | "end" | "start">("move");
  const [draft, setDraft] = useState<{ start: Point; end: Point } | null>(null);
  useLocate("box", props.locate, setSelected);
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
  const defaults = () =>
    withDefaults({}, attributeFields(props.template, "object"));
  function add() {
    append({
      category,
      x1: width * 0.1,
      y1: height * 0.1,
      x2: width * 0.3,
      y2: height * 0.3,
      attributes: defaults(),
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
        const delta = arrowDelta(event.key, keyStep(event));
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
        } else if (event.key.toLowerCase() === "r" && current) {
          event.preventDefault();
          setEdge(
            ({ move: "end", end: "start", start: "move" } as const)[edge],
          );
        } else if (delta && current) {
          event.preventDefault();
          update(
            edge === "end"
              ? resizeBox(current, delta.x, delta.y, width, height)
              : edge === "start"
                ? resizeBoxStart(current, delta.x, delta.y)
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
      {labels.length === 0 && <p role="status">{t("wbEditorNoLabels")}</p>}
      <ImageCanvas
        width={width}
        height={height}
        mediaUrl={props.mediaUrl}
        thumbnailUrl={props.thumbnailUrl}
        toolbar={
          <BoxToolbar
            labels={labels}
            template={props.template}
            boxes={boxes}
            selected={current ? selected : -1}
            category={current?.category ?? category}
            readOnly={readOnly}
            onLabel={(next) => {
              setLabel(next);
              if (current) update({ ...current, category: next });
            }}
            onSelect={setSelected}
            onAdd={add}
            onCopy={copy}
            onDelete={remove}
            keyMode={
              {
                move: t("wbKeysMoveBox"),
                end: t("wbKeysBoxEnd"),
                start: t("wbKeysBoxStart"),
              }[edge]
            }
          />
        }
        onStart={(point) => {
          if (!readOnly && category) setDraft({ start: point, end: point });
        }}
        onMove={(point) => {
          if (draft) setDraft({ ...draft, end: point });
        }}
        onFinish={(point) => {
          if (!draft) return;
          const box = boxFromPoints(draft.start, point, category);
          if (box.x2 - box.x1 >= 1 && box.y2 - box.y1 >= 1)
            append({ ...box, attributes: defaults() });
          setDraft(null);
        }}
      >
        {boxes.map((box, index) => (
          <BoxShape
            key={index}
            value={box}
            selected={index === selected}
            style={labelStyle(labels, box.category, tokens)}
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
            stroke={labelStyle(labels, category, tokens).stroke}
            strokeWidth={2}
            strokeScaleEnabled={false}
            listening={false}
            dash={[4, 4]}
          />
        )}
        <ShapeLabels
          chips={boxes.map((box) => ({
            ...boxChipAnchor(box),
            style: labelStyle(labels, box.category, tokens),
          }))}
        />
      </ImageCanvas>
      <BoxDetails
        {...props}
        current={current}
        width={width}
        height={height}
        onUpdate={update}
      />
    </KeyboardRegion>
  );
}
