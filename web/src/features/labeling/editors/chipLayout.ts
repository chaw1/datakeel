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

/** Where a shape's chip is anchored, and the shape's bounds that limit and place it. */
export interface ChipAnchor {
  x: number;
  y: number;
  bounds: Bounds;
}

/** A box's chip anchors at its top-left corner. */
export function boxChipAnchor(box: Bounds): ChipAnchor {
  return {
    x: box.x1,
    y: box.y1,
    bounds: { x1: box.x1, y1: box.y1, x2: box.x2, y2: box.y2 },
  };
}

/** A polygon's chip anchors at its topmost vertex (leftmost on ties). */
export function polygonChipAnchor(
  points: readonly { x: number; y: number }[],
): ChipAnchor {
  const top = points.reduce(
    (best, point) =>
      point.y < best.y || (point.y === best.y && point.x < best.x)
        ? point
        : best,
    points[0] ?? { x: 0, y: 0 },
  );
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  return {
    x: top.x,
    y: top.y,
    bounds: {
      x1: Math.min(...xs),
      y1: Math.min(...ys),
      x2: Math.max(...xs),
      y2: Math.max(...ys),
    },
  };
}

export interface ChipHit {
  rect: { x: number; y: number; width: number; height: number };
  name: string;
  truncated: boolean;
}

function contains(
  rect: ChipHit["rect"],
  pointer: { x: number; y: number },
): boolean {
  return (
    pointer.x >= rect.x &&
    pointer.x <= rect.x + rect.width &&
    pointer.y >= rect.y &&
    pointer.y <= rect.y + rect.height
  );
}

/**
 * The full name to show for the pointer position, read from the topmost chip under it (chips
 * come in drawing order, last on top). It is shown when that chip is truncated, or when it
 * overlaps another chip there, so the tooltip always names the chip the user sees on top. A
 * lone chip that already shows its whole name needs no tooltip.
 * Chips never take pointer events, so presses reach the canvas or shape beneath them.
 */
export function chipTitleAt(
  chips: readonly ChipHit[],
  pointer: { x: number; y: number },
): string | null {
  const under = chips.filter((chip) => contains(chip.rect, pointer));
  const top = under.at(-1);
  if (!top) return null;
  return top.truncated || under.length > 1 ? top.name : null;
}
