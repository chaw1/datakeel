/** Screen-space size and placement of the label-name chip drawn at each shape. */

export const CHIP_FONT_SIZE = 12;
export const CHIP_PADDING = 3;
export const CHIP_HEIGHT = CHIP_FONT_SIZE + CHIP_PADDING * 2;
export const CHIP_MIN_WIDTH = 56;
export const CHIP_MAX_WIDTH = 160;

export interface Bounds {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/**
 * The widest a chip may be on screen: its own shape's on-screen width, kept between the
 * minimum and maximum, so a long name cannot run over the chip of a shape to its right.
 */
export function chipLimit(shapeScreenWidth: number): number {
  return Math.min(CHIP_MAX_WIDTH, Math.max(CHIP_MIN_WIDTH, shapeScreenWidth));
}

function intersects(shape: Bounds, visible: Bounds): boolean {
  return (
    shape.x2 > visible.x1 &&
    shape.x1 < visible.x2 &&
    shape.y2 > visible.y1 &&
    shape.y1 < visible.y2
  );
}

/**
 * Image-space top-left of a chip anchored at the shape's top-left corner. It sits above the
 * shape when the image has room, otherwise just inside the top edge. While any part of the
 * shape is visible, the chip is pulled inside the visible area so the name stays readable.
 */
export function chipPosition(
  anchor: { x: number; y: number },
  shape: Bounds,
  visible: Bounds | null,
  size: { width: number; height: number },
): { x: number; y: number } {
  const x = anchor.x;
  const y = anchor.y >= size.height ? anchor.y - size.height : anchor.y;
  if (!visible || !intersects(shape, visible)) return { x, y };
  return {
    x: Math.max(Math.min(x, visible.x2 - size.width), visible.x1),
    y: Math.max(Math.min(y, visible.y2 - size.height), visible.y1),
  };
}
