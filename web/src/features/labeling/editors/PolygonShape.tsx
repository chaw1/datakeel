import { Circle, Line } from "react-konva";

import { clamp, movePoints } from "./geometry";
import { ShapeLabel } from "./ShapeLabel";

import type { LabelStyle } from "./labelColors";
import type { AnnotationPolygon } from "./types";

export function PolygonShape({
  value,
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
  value: AnnotationPolygon;
  selected: boolean;
  selectedPoint: number;
  style: LabelStyle;
  width: number;
  height: number;
  readOnly?: boolean;
  onSelect: () => void;
  onPoint: (index: number) => void;
  onChange: (value: AnnotationPolygon) => void;
}) {
  // Anchor the name at the topmost vertex (leftmost on ties).
  const top = value.points.reduce(
    (best, point) =>
      point.y < best.y || (point.y === best.y && point.x < best.x)
        ? point
        : best,
    value.points[0] ?? { x: 0, y: 0 },
  );
  return (
    <>
      <Line
        closed
        points={value.points.flatMap((point) => [point.x, point.y])}
        stroke={style.stroke}
        fill={style.fill}
        strokeWidth={selected ? 3 : 2}
        strokeScaleEnabled={false}
        draggable={!readOnly}
        onClick={onSelect}
        onTap={onSelect}
        onDragStart={onSelect}
        onDragEnd={(event) => {
          const points = movePoints(
            value.points,
            event.target.x(),
            event.target.y(),
            width,
            height,
          );
          event.target.position({ x: 0, y: 0 });
          onChange({ ...value, points });
        }}
      />
      <ShapeLabel
        x={top.x}
        y={top.y}
        bounds={{
          x1: Math.min(...value.points.map((point) => point.x)),
          y1: Math.min(...value.points.map((point) => point.y)),
          x2: Math.max(...value.points.map((point) => point.x)),
          y2: Math.max(...value.points.map((point) => point.y)),
        }}
        style={style}
      />
      {selected &&
        value.points.map((point, index) => (
          <Circle
            key={index}
            x={point.x}
            y={point.y}
            radius={
              Math.max(width, height) / (index === selectedPoint ? 100 : 140)
            }
            stroke={style.stroke}
            fill={style.stroke}
            strokeWidth={2}
            strokeScaleEnabled={false}
            draggable={!readOnly}
            onClick={() => {
              onPoint(index);
            }}
            onTap={() => {
              onPoint(index);
            }}
            onDragStart={() => {
              onPoint(index);
            }}
            onDragEnd={(event) => {
              const position = {
                x: clamp(event.target.x(), width),
                y: clamp(event.target.y(), height),
              };
              event.target.position(position);
              onChange({
                ...value,
                points: value.points.map((item, i) =>
                  i === index ? position : item,
                ),
              });
            }}
          />
        ))}
    </>
  );
}
