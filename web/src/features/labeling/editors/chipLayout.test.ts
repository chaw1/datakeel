import { expect, it } from "vitest";

import {
  CHIP_MAX_WIDTH,
  CHIP_MIN_WIDTH,
  chipLimit,
  chipPosition,
} from "./chipLayout";

const size = { width: 40, height: 10 };

it("limits a chip to its shape's on-screen width within the minimum and maximum", () => {
  expect(chipLimit(90)).toBe(90);
  expect(chipLimit(12)).toBe(CHIP_MIN_WIDTH);
  expect(chipLimit(900)).toBe(CHIP_MAX_WIDTH);
});

it("sits above the shape when there is room, otherwise just inside its top edge", () => {
  const shape = { x1: 100, y1: 50, x2: 300, y2: 200 };
  expect(chipPosition({ x: 100, y: 50 }, shape, null, size)).toEqual({
    x: 100,
    y: 40,
  });
  expect(
    chipPosition({ x: 100, y: 4 }, { ...shape, y1: 4 }, null, size),
  ).toEqual({ x: 100, y: 4 });
});

it("pulls the chip inside the visible area while part of the shape is on screen", () => {
  const shape = { x1: 100, y1: 50, x2: 300, y2: 200 };
  // Zoomed in on the shape's lower right: its top-left corner is off screen.
  const visible = { x1: 180, y1: 120, x2: 400, y2: 260 };
  expect(chipPosition({ x: 100, y: 50 }, shape, visible, size)).toEqual({
    x: 180,
    y: 120,
  });
  // Near the right and bottom edges the chip moves back inside instead of being cut off.
  const corner = { x1: 380, y1: 255, x2: 600, y2: 400 };
  expect(chipPosition({ x: 380, y: 255 }, corner, visible, size)).toEqual({
    x: 360,
    y: 245,
  });
});

it("leaves a chip alone when its shape is entirely off screen", () => {
  const shape = { x1: 0, y1: 0, x2: 50, y2: 50 };
  const visible = { x1: 180, y1: 120, x2: 400, y2: 260 };
  expect(chipPosition({ x: 0, y: 0 }, shape, visible, size)).toEqual({
    x: 0,
    y: 0,
  });
});
