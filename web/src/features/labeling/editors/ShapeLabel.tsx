import { useContext } from "react";
import { Label, Tag, Text } from "react-konva";

import { CanvasScaleContext } from "./editorContext";

import type { LabelStyle } from "./labelColors";

const FONT_SIZE = 12;
const PADDING = 3;
const CHIP_HEIGHT = FONT_SIZE + PADDING * 2;

/** A label-name chip that keeps the same on-screen size at every zoom level. */
export function ShapeLabel({
  x,
  y,
  style,
}: {
  x: number;
  y: number;
  style: LabelStyle;
}) {
  const scale = useContext(CanvasScaleContext);
  const inverse = scale > 0 ? 1 / scale : 1;
  // Sit above the shape when there is room, otherwise just inside its top edge.
  const above = y * scale >= CHIP_HEIGHT;
  return (
    <Label
      x={x}
      y={y}
      scaleX={inverse}
      scaleY={inverse}
      offsetY={above ? CHIP_HEIGHT : 0}
      listening={false}
      name="wb-shape-label"
    >
      <Tag fill={style.stroke} cornerRadius={2} />
      <Text
        text={style.name}
        fontSize={FONT_SIZE}
        padding={PADDING}
        fill={style.text}
        fontStyle="bold"
      />
    </Label>
  );
}
