import { useState } from "react";

import { useI18n } from "../../../i18n/useI18n";

import { attributeFields, withDefaults } from "./attributes";
import { polygonChips } from "./chipLayout";
import { arrowDelta, clamp, isTyping, keyStep } from "./geometry";
import { ImageCanvas } from "./ImageCanvas";
import { KeyboardRegion } from "./KeyboardRegion";
import { KeypointDetails } from "./KeypointDetails";
import {
  blankSkeleton,
  firstMissing,
  normalizeSkeleton,
  positioned,
  templateSkeleton,
} from "./keypoints";
import { KeypointShape } from "./KeypointShape";
import { KeypointToolbar } from "./KeypointToolbar";
import { labelStyle } from "./labelColors";
import { ShapeLabels } from "./ShapeLabels";
import { shortcutLabel } from "./shortcuts";
import { useCanvasTokens } from "./useCanvasTokens";

import type {
  AnnotationKeypoint,
  AnnotationSkeleton,
  EditorProps,
  Point,
} from "./types";

export function KeypointEditor(props: EditorProps) {
  const { value, labels, onChange, readOnly } = props;
  const { t } = useI18n();
  const tokens = useCanvasTokens();
  const schema = templateSkeleton(props.template);
  const width = value.image_width ?? 2000;
  const height = value.image_height ?? 1500;
  const [selected, setSelected] = useState(-1);
  const [pointIndex, setPointIndex] = useState(0);
  const [label, setLabel] = useState(labels[0]?.id ?? "");
  const [cursor, setCursor] = useState<Point>({ x: width / 2, y: height / 2 });
  const skeletons = (value.keypoints ?? []).map((skeleton) =>
    schema ? normalizeSkeleton(skeleton, schema) : skeleton,
  );
  const selectedIndex = Math.min(selected, skeletons.length - 1);
  const current = selectedIndex >= 0 ? skeletons.at(selectedIndex) : undefined;
  const category = current?.category ?? label;
  const safePoint = Math.min(pointIndex, (schema?.points.length ?? 1) - 1);
  if (!schema)
    return (
      <section
        className="wb-annotation-editor"
        aria-label={t("wbEditorKeypoints")}
      >
        <p role="alert">{t("wbKeypointSchemaMissing")}</p>
      </section>
    );
  function change(next: AnnotationSkeleton[]) {
    if (!readOnly)
      onChange({
        ...value,
        image_width: width,
        image_height: height,
        keypoints: next,
      });
  }
  function update(skeleton: AnnotationSkeleton) {
    change(
      skeletons.map((item, index) =>
        index === selectedIndex ? skeleton : item,
      ),
    );
  }
  function updatePoint(point: AnnotationKeypoint) {
    if (!current) return;
    update({
      ...current,
      points: current.points.map((item, index) =>
        index === safePoint ? point : item,
      ),
    });
  }
  function select(index: number) {
    setSelected(index);
    setPointIndex(firstMissing(skeletons.at(index)));
  }
  function add() {
    if (readOnly || !category || !schema) return;
    const skeleton = blankSkeleton(
      category,
      schema,
      withDefaults({}, attributeFields(props.template, "object")),
    );
    change([...skeletons, skeleton]);
    setSelected(skeletons.length);
    setPointIndex(0);
  }
  function remove() {
    if (readOnly || !current) return;
    change(skeletons.filter((_, index) => index !== selectedIndex));
    setSelected(Math.min(selectedIndex, skeletons.length - 2));
    setPointIndex(0);
  }
  function place(position: Point) {
    if (readOnly || !category || !schema) return;
    setCursor(position);
    const base = current ?? blankSkeleton(category, schema, {});
    const target = current ? safePoint : firstMissing(base);
    const next = {
      ...base,
      points: base.points.map((point, index) =>
        index === target
          ? {
              ...point,
              x: position.x,
              y: position.y,
              state: "visible" as const,
            }
          : point,
      ),
    };
    if (current) update(next);
    else {
      change([...skeletons, next]);
      setSelected(skeletons.length);
    }
    const missing = next.points.findIndex((point) => point.state === "missing");
    setPointIndex(missing < 0 ? target : missing);
  }
  function markMissing() {
    if (current)
      updatePoint({
        ...current.points[safePoint],
        state: "missing",
        x: null,
        y: null,
      });
  }
  function cycleState() {
    if (!current) return;
    const point = current.points[safePoint];
    if (!positioned(point)) {
      place(cursor);
      return;
    }
    updatePoint({
      ...point,
      state: point.state === "visible" ? "occluded" : "visible",
    });
  }
  const chips = polygonChips(
    skeletons.map((skeleton) => ({
      category: skeleton.category,
      points: skeleton.points.filter(positioned),
    })),
    labels,
    tokens,
  );
  return (
    <KeyboardRegion
      label={t("wbEditorKeypoints")}
      onKeyDown={(event) => {
        if (
          readOnly ||
          isTyping(event.target) ||
          event.ctrlKey ||
          event.metaKey ||
          event.altKey ||
          (event.target instanceof HTMLButtonElement && event.key === " ")
        )
          return;
        const delta = arrowDelta(event.key, keyStep(event));
        if (event.key.toLowerCase() === "k") {
          event.preventDefault();
          add();
        } else if (event.key === " ") {
          event.preventDefault();
          place(cursor);
        } else if (event.key.toLowerCase() === "v") {
          event.preventDefault();
          cycleState();
        } else if (event.key.toLowerCase() === "x") {
          event.preventDefault();
          markMissing();
        } else if (["[", "]"].includes(event.key) && current) {
          event.preventDefault();
          setPointIndex(
            (safePoint + (event.key === "]" ? 1 : -1) + schema.points.length) %
              schema.points.length,
          );
        } else if (delta) {
          event.preventDefault();
          const point = current?.points.at(safePoint);
          if (point && positioned(point))
            updatePoint({
              ...point,
              x: clamp(point.x + delta.x, width),
              y: clamp(point.y + delta.y, height),
            });
          else
            setCursor({
              x: clamp(cursor.x + delta.x, width),
              y: clamp(cursor.y + delta.y, height),
            });
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
          <KeypointToolbar
            labels={labels}
            template={props.template}
            skeletons={skeletons}
            selected={selectedIndex}
            category={category}
            readOnly={readOnly}
            onSelect={select}
            onAdd={add}
            onDelete={remove}
            onLabel={(next) => {
              setLabel(next);
              if (current) update({ ...current, category: next });
            }}
          />
        }
        onStart={place}
        onMove={setCursor}
      >
        {skeletons.map((skeleton, index) => (
          <KeypointShape
            key={index}
            value={skeleton}
            schema={schema}
            selected={index === selectedIndex}
            selectedPoint={safePoint}
            style={labelStyle(labels, skeleton.category, tokens)}
            width={width}
            height={height}
            readOnly={readOnly}
            onSelect={() => {
              select(index);
            }}
            onPoint={setPointIndex}
            onChange={(next) => {
              change(skeletons.map((item, i) => (i === index ? next : item)));
            }}
          />
        ))}
        <ShapeLabels chips={chips} />
      </ImageCanvas>
      <KeypointDetails
        {...props}
        current={current}
        schema={schema}
        pointIndex={safePoint}
        width={width}
        height={height}
        onPoint={setPointIndex}
        onPointChange={updatePoint}
        onUpdate={update}
      />
    </KeyboardRegion>
  );
}
