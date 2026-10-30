/** Screen-space size and placement of the label-name chip drawn at each shape. */

export const CHIP_FONT_SIZE = 12;
export const CHIP_PADDING = 3;
export const CHIP_HEIGHT = CHIP_FONT_SIZE + CHIP_PADDING * 2;
export const CHIP_MIN_WIDTH = 56;
export const CHIP_MAX_WIDTH = 160;
/** Konva node name shared by every label chip, used to find chips under the pointer. */
export const CHIP_NAME = "wb-shape-label";

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

export interface ChipHit {
  rect: { x: number; y: number; width: number; height: number };
  name: string;
  truncated: boolean;
}

/**
 * The full name to show for the pointer position: the topmost truncated chip under it.
 * Chips never take pointer events, so presses reach the canvas or shape beneath them.
 */
export function chipTitleAt(
  chips: readonly ChipHit[],
  pointer: { x: number; y: number },
): string | null {
  for (const chip of [...chips].reverse()) {
    const { x, y, width, height } = chip.rect;
    if (
      chip.truncated &&
      pointer.x >= x &&
      pointer.x <= x + width &&
      pointer.y >= y &&
      pointer.y <= y + height
    )
      return chip.name;
  }
  return null;
}
