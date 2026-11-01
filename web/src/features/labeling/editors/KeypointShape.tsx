import { use } from "react";
import { Circle, Line } from "react-konva";

import { CanvasScaleContext, CanvasViewContext } from "./editorContext";
import { clamp } from "./geometry";
import { positioned } from "./keypoints";

import type { LabelStyle } from "./labelColors";
import type { AnnotationSkeleton, SkeletonDefinition } from "./types";

export function KeypointShape({
  value,
  schema,
  selected,
  selectedPoint,
  style,
  width,
  height,
  readOnly,
  onSelect,
  onPoint,
  onChange,
}: {
  value: AnnotationSkeleton;
  schema: SkeletonDefinition;
  selected: boolean;
  selectedPoint: number;
  style: LabelStyle;
  width: number;
  height: number;
  readOnly?: boolean;
  onSelect: () => void;
  onPoint: (index: number) => void;
  onChange: (value: AnnotationSkeleton) => void;
}) {
  const scale = use(CanvasScaleContext);
  const visible = use(CanvasViewContext);
  const points = value.points.filter(positioned);
  if (visible && points.length) {
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const margin = 12 / scale;
    if (
      Math.max(...xs) < visible.x1 - margin ||
      Math.min(...xs) > visible.x2 + margin ||
      Math.max(...ys) < visible.y1 - margin ||
      Math.min(...ys) > visible.y2 + margin
    )
      return null;
  }
  const radius = (selected ? 7 : 5) / scale;
  return (
    <>
      {schema.edges.map(([left, right]) => {
        const first = value.points.find((point) => point.id === left);
        const second = value.points.find((point) => point.id === right);
        if (!first || !second || !positioned(first) || !positioned(second))
          return null;
        return (
          <Line
            key={`${left}:${right}`}
            points={[first.x, first.y, second.x, second.y]}
            stroke={style.stroke}
            strokeWidth={selected ? 3 : 2}
            strokeScaleEnabled={false}
            listening={false}
          />
        );
      })}
      {value.points.map((point, index) => {
        if (!positioned(point)) return null;
        return (
          <Circle
            key={point.id}
            x={point.x}
            y={point.y}
            radius={
              index === selectedPoint && selected ? radius * 1.35 : radius
            }
            stroke={style.stroke}
            fill={point.state === "visible" ? style.stroke : "transparent"}
            dash={point.state === "occluded" ? [3 / scale, 3 / scale] : []}
            strokeWidth={index === selectedPoint && selected ? 3 : 2}
            strokeScaleEnabled={false}
            hitStrokeWidth={18 / scale}
            draggable={!readOnly}
            onClick={() => {
              onSelect();
              onPoint(index);
            }}
            onTap={() => {
              onSelect();
              onPoint(index);
            }}
            onDragStart={() => {
              onSelect();
              onPoint(index);
            }}
            onDragEnd={(event) => {
              const x = clamp(event.target.x(), width);
              const y = clamp(event.target.y(), height);
              event.target.position({ x, y });
              onChange({
                ...value,
                points: value.points.map((item, pointIndex) =>
                  pointIndex === index ? { ...item, x, y } : item,
                ),
              });
            }}
          />
        );
      })}
    </>
  );
}
