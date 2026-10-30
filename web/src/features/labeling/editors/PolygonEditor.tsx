import { useState } from "react";
import { Circle, Line } from "react-konva";

import { useI18n } from "../../../i18n/useI18n";

import { attributeFields, withDefaults } from "./attributes";
import { polygonChipAnchor } from "./chipLayout";
import { EditorDetails } from "./EditorDetails";
import { arrowDelta, clamp, isTyping, keyStep, movePoints } from "./geometry";
import { ImageCanvas } from "./ImageCanvas";
import { KeyboardRegion } from "./KeyboardRegion";
import { labelStyle } from "./labelColors";
import { PolygonToolbar } from "./PolygonControls";
import { PolygonDetails } from "./PolygonDetails";
import { PolygonShape } from "./PolygonShape";
import { ShapeLabels } from "./ShapeLabels";
import { shortcutLabel } from "./shortcuts";
import { useCanvasTokens } from "./useCanvasTokens";

import type { PolygonControlProps } from "./PolygonControls";
import type { AnnotationPolygon, EditorProps, Point } from "./types";

export function PolygonEditor(props: EditorProps) {
  const { value, labels, onChange, readOnly } = props;
  const { t } = useI18n();
  const tokens = useCanvasTokens();
  const width = value.image_width ?? 2000,
    height = value.image_height ?? 1500;
  const polygons = value.polygons ?? [];
  const [selected, setSelected] = useState(-1);
  const [pointIndex, setPointIndex] = useState(0);
  // R switches the arrows between moving the whole polygon and its selected point.
  const [vertexMode, setVertexMode] = useState(false);
  const [label, setLabel] = useState(labels[0]?.id ?? "");
  const [cursor, setCursor] = useState<Point>({ x: width / 2, y: height / 2 });
  const [draft, setDraft] = useState<Point[] | null>(null);
  const current = selected >= 0 ? polygons.at(selected) : undefined;
  const category = labels.some((item) => item.id === label)
    ? label
    : (labels[0]?.id ?? "");
  function update(polygon: AnnotationPolygon) {
    if (!readOnly)
      onChange({
        ...value,
        polygons: polygons.map((item, index) =>
          index === selected ? polygon : item,
        ),
      });
  }
  function finish() {
    if (readOnly || !draft || draft.length < 3 || !category) return;
    onChange({
      ...value,
      image_width: width,
      image_height: height,
      polygons: [
        ...polygons,
        {
          category,
          points: draft,
          attributes: withDefaults(
            {},
            attributeFields(props.template, "object"),
          ),
        },
      ],
    });
    setSelected(polygons.length);
    setPointIndex(0);
    setDraft(null);
  }
  function remove() {
    if (readOnly || !current) return;
    onChange({
      ...value,
      polygons: polygons.filter((_, index) => index !== selected),
    });
    setSelected(Math.min(selected, polygons.length - 2));
    setPointIndex(0);
  }
  function removePoint() {
    if (!current || current.points.length <= 3) return;
    update({
      ...current,
      points: current.points.filter((_, index) => index !== pointIndex),
    });
    setPointIndex(Math.max(0, pointIndex - 1));
  }
  function start() {
    if (current) setLabel(current.category);
    setSelected(-1);
    setDraft([]);
  }
  function addPoint(point = cursor) {
    if (readOnly || !category) return;
    if (draft === null) {
      if (current) setLabel(current.category);
      setSelected(-1);
    }
    setCursor(point);
    setDraft((points) => [...(points ?? []), point]);
  }
  const drawStroke = labelStyle(labels, category, tokens).stroke;
  const controls: PolygonControlProps = {
    template: props.template,
    labels: labels,
    polygons: polygons,
    selected: selected,
    category: category,
    pointIndex: pointIndex,
    cursor: cursor,
    draft: draft,
    width: width,
    height: height,
    readOnly: readOnly,
    advancedAttributes: props.advancedAttributes,
    keyMode:
      draft !== null
        ? t("wbKeysCursor")
        : vertexMode
          ? t("wbKeysPoint")
          : t("wbKeysMovePolygon"),
    onSelect: (index) => {
      setSelected(index);
      setPointIndex(0);
    },
    onPoint: setPointIndex,
    onLabel: (next) => {
      setLabel(next);
      if (current) update({ ...current, category: next });
    },
    onCursor: setCursor,
    onStart: start,
    onAddPoint: () => {
      addPoint();
    },
    onFinish: finish,
    onCancel: () => {
      setDraft(null);
    },
    onDelete: remove,
    onDeletePoint: removePoint,
    onChange: update,
  };
  return (
    <KeyboardRegion
      label={t("wbEditorPolygon")}
      onKeyDown={(event) => {
        if (
          readOnly ||
          isTyping(event.target) ||
          event.ctrlKey ||
          event.metaKey ||
          event.altKey
        )
          return;
        if (
          event.target instanceof HTMLButtonElement &&
          ["Enter", " "].includes(event.key)
        )
          return;
        const delta = arrowDelta(event.key, keyStep(event));
        if (event.key.toLowerCase() === "p") {
          event.preventDefault();
          start();
        } else if (event.key === "Escape") {
          event.preventDefault();
          setDraft(null);
        } else if (event.key === "Enter" && draft !== null) {
          event.preventDefault();
          finish();
        } else if (event.key === " " && draft !== null) {
          event.preventDefault();
          addPoint();
        } else if (event.key.toLowerCase() === "r" && current) {
          event.preventDefault();
          setVertexMode(!vertexMode);
        } else if (event.key === "Delete") {
          event.preventDefault();
          remove();
        } else if (event.key === "Backspace" && current) {
          event.preventDefault();
          removePoint();
        } else if (delta) {
          event.preventDefault();
          if (draft !== null)
            setCursor({
              x: clamp(cursor.x + delta.x, width),
              y: clamp(cursor.y + delta.y, height),
            });
          else if (current && vertexMode) {
            update({
              ...current,
              points: current.points.map((point, index) =>
                index === pointIndex
                  ? {
                      x: clamp(point.x + delta.x, width),
                      y: clamp(point.y + delta.y, height),
                    }
                  : point,
              ),
            });
          } else if (current)
            update({
              ...current,
              points: movePoints(
                current.points,
                delta.x,
                delta.y,
                width,
                height,
              ),
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
        toolbar={<PolygonToolbar {...controls} />}
        drawing={draft !== null}
        onStart={addPoint}
        onMove={(point) => {
          if (draft !== null) setCursor(point);
        }}
      >
        {polygons.map((polygon, index) => (
          <PolygonShape
            key={index}
            value={polygon}
            selected={selected === index}
            selectedPoint={pointIndex}
            style={labelStyle(labels, polygon.category, tokens)}
            width={width}
            height={height}
            readOnly={readOnly}
            onSelect={() => {
              setSelected(index);
            }}
            onPoint={setPointIndex}
            onChange={(next) => {
              if (!readOnly)
                onChange({
                  ...value,
                  polygons: polygons.map((item, i) =>
                    i === index ? next : item,
                  ),
                });
            }}
          />
        ))}
        {draft !== null && (
          <>
            <Line
              points={[...draft, cursor].flatMap((point) => [point.x, point.y])}
              stroke={drawStroke}
              strokeWidth={2}
              strokeScaleEnabled={false}
              listening={false}
              dash={[4, 4]}
            />
            <Circle
              x={cursor.x}
              y={cursor.y}
              radius={Math.max(width, height) / 140}
              stroke={drawStroke}
              strokeWidth={2}
              strokeScaleEnabled={false}
              listening={false}
            />
          </>
        )}
        <ShapeLabels
          chips={polygons.map((polygon) => ({
            ...polygonChipAnchor(polygon.points),
            style: labelStyle(labels, polygon.category, tokens),
          }))}
        />
      </ImageCanvas>
      <EditorDetails label={t("wbEditorPolygon")}>
        <p className="muted">{t("wbEditorPolygonHint")}</p>
        <PolygonDetails {...controls} />
      </EditorDetails>
    </KeyboardRegion>
  );
}
