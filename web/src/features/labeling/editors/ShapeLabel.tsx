import { useContext, useLayoutEffect, useRef, useState } from "react";
import { Label, Tag, Text } from "react-konva";

import {
  CHIP_FONT_SIZE,
  CHIP_HEIGHT,
  CHIP_NAME,
  CHIP_PADDING,
  chipLimit,
  chipPosition,
} from "./chipLayout";
import { CanvasScaleContext, CanvasViewContext } from "./editorContext";

import type { Bounds } from "./chipLayout";
import type { LabelStyle } from "./labelColors";
import type Konva from "konva";

/**
 * A label-name chip that keeps the same on-screen size at every zoom level. A name wider than
 * the chip ends in an ellipsis; ImageCanvas shows it in full on hover.
 */
export function ShapeLabel({
  x,
  y,
  bounds,
  style,
}: {
  x: number;
  y: number;
  bounds: Bounds;
  style: LabelStyle;
}) {
  const scale = useContext(CanvasScaleContext);
  const visible = useContext(CanvasViewContext);
  const inverse = scale > 0 ? 1 / scale : 1;
  const text = useRef<Konva.Text>(null);
  // The name's natural width, measured while it is drawn without a width limit.
  const [natural, setNatural] = useState<{ name: string; width: number }>();
  const measured = natural?.name === style.name ? natural.width : null;
  useLayoutEffect(() => {
    if (measured === null && text.current)
      setNatural({ name: style.name, width: text.current.getTextWidth() });
  }, [measured, style.name]);
  const limit = chipLimit((bounds.x2 - bounds.x1) * scale);
  const full = measured === null ? null : measured + CHIP_PADDING * 2;
  const truncated = full !== null && full > limit;
  const width = truncated ? limit : (full ?? 0);
  const position = chipPosition({ x, y }, bounds, visible, {
    width: width * inverse,
    height: CHIP_HEIGHT * inverse,
  });
  return (
    <Label
      x={position.x}
      y={position.y}
      scaleX={inverse}
      scaleY={inverse}
      // Presses pass through to the canvas or shape beneath; ImageCanvas shows the full name
      // of a truncated chip on hover by hit-testing chips itself.
      listening={false}
      name={CHIP_NAME}
    >
      <Tag fill={style.stroke} cornerRadius={2} />
      <Text
        ref={text}
        text={style.name}
        fontSize={CHIP_FONT_SIZE}
        padding={CHIP_PADDING}
        fill={style.text}
        fontStyle="bold"
        wrap="none"
        ellipsis={truncated}
        {...(truncated ? { width: limit } : {})}
      />
    </Label>
  );
}
