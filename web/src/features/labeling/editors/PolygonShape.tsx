import { Circle, Line } from "react-konva";

import { clamp, movePoints } from "./geometry";

import type { AnnotationPolygon } from "./types";

export function PolygonShape({
  value,
  selected,
  selectedPoint,
  color,
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
  color: string;
  width: number;
  height: number;
  readOnly?: boolean;
  onSelect: () => void;
  onPoint: (index: number) => void;
  onChange: (value: AnnotationPolygon) => void;
}) {
  return (
    <>
      <Line
        closed
        points={value.points.flatMap((point) => [point.x, point.y])}
        stroke={color}
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
      {selected &&
        value.points.map((point, index) => (
          <Circle
            key={index}
            x={point.x}
            y={point.y}
            radius={
              Math.max(width, height) / (index === selectedPoint ? 100 : 140)
            }
            stroke={color}
            fill={color}
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
