import { useEffect, useRef } from "react";
import { Rect, Transformer } from "react-konva";

import { clamp, moveBox } from "./geometry";

import type { LabelStyle } from "./labelColors";
import type { AnnotationBox } from "./types";
import type Konva from "konva";

export function BoxShape({
  value,
  selected,
  style,
  width,
  height,
  readOnly,
  onSelect,
  onChange,
}: {
  value: AnnotationBox;
  selected: boolean;
  style: LabelStyle;
  width: number;
  height: number;
  readOnly?: boolean;
  onSelect: () => void;
  onChange: (value: AnnotationBox) => void;
}) {
  const rectangle = useRef<Konva.Rect>(null);
  const transformer = useRef<Konva.Transformer>(null);
  useEffect(() => {
    if (selected && rectangle.current && transformer.current) {
      transformer.current.nodes([rectangle.current]);
      transformer.current.getLayer()?.batchDraw();
    }
  }, [selected]);
  return (
    <>
      <Rect
        ref={rectangle}
        x={value.x1}
        y={value.y1}
        width={value.x2 - value.x1}
        height={value.y2 - value.y1}
        stroke={style.stroke}
        fill={style.fill}
        strokeWidth={selected ? 3 : 2}
        strokeScaleEnabled={false}
        draggable={!readOnly}
        onClick={onSelect}
        onTap={onSelect}
        onDragStart={onSelect}
        onDragEnd={(event) => {
          const next = moveBox(
            value,
            event.target.x() - value.x1,
            event.target.y() - value.y1,
            width,
            height,
          );
          event.target.position({ x: next.x1, y: next.y1 });
          onChange(next);
        }}
        onTransformEnd={() => {
          const node = rectangle.current;
          if (!node) return;
          const x1 = clamp(node.x(), width - 1),
            y1 = clamp(node.y(), height - 1);
          const x2 = Math.max(
            x1 + 1,
            clamp(node.x() + node.width() * node.scaleX(), width),
          );
          const y2 = Math.max(
            y1 + 1,
            clamp(node.y() + node.height() * node.scaleY(), height),
          );
          node.position({ x: x1, y: y1 });
          node.size({ width: x2 - x1, height: y2 - y1 });
          node.scale({ x: 1, y: 1 });
          onChange({ ...value, x1, y1, x2, y2 });
        }}
      />
      {selected && !readOnly && (
        <Transformer
          ref={transformer}
          rotateEnabled={false}
          flipEnabled={false}
          anchorStroke={style.stroke}
          borderStroke={style.stroke}
          anchorSize={8}
          boundBoxFunc={(oldBox, newBox) =>
            newBox.width >= 2 && newBox.height >= 2 ? newBox : oldBox
          }
        />
      )}
    </>
  );
}
