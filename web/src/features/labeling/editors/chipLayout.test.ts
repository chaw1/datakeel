import { expect, it } from "vitest";

import {
  CHIP_MAX_WIDTH,
  CHIP_MIN_WIDTH,
  boxChipAnchor,
  chipLimit,
  chipPosition,
  chipTitleAt,
  polygonChipAnchor,
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

it("names a truncated chip under the pointer and nothing elsewhere", () => {
  const rect = { x: 10, y: 10, width: 100, height: 18 };
  const long = { rect, name: "Refrigerated beverage display", truncated: true };
  const short = { rect, name: "Cat", truncated: false };
  expect(chipTitleAt([long], { x: 50, y: 20 })).toBe(long.name);
  expect(chipTitleAt([long], { x: 111, y: 20 })).toBeNull();
  expect(chipTitleAt([long], { x: 50, y: 29 })).toBeNull();
  expect(chipTitleAt([short], { x: 50, y: 20 })).toBeNull();
});

it("names the chip drawn on top where chips overlap", () => {
  const rect = { x: 10, y: 10, width: 100, height: 18 };
  const long = { rect, name: "Refrigerated beverage display", truncated: true };
  const top = { ...long, name: "Shopping cart with handle" };
  expect(chipTitleAt([long, top], { x: 50, y: 20 })).toBe(top.name);
  // A whole short name drawn over a cut-off one is what the user sees, so it is named.
  const short = { rect, name: "Cat", truncated: false };
  expect(chipTitleAt([long, short], { x: 50, y: 20 })).toBe(short.name);
  const dog = { rect, name: "Dog", truncated: false };
  expect(chipTitleAt([dog, short], { x: 50, y: 20 })).toBe(short.name);
  // Where the later chip ends, the pointer is over the earlier one alone.
  const right = { ...short, rect: { ...rect, x: 80 } };
  expect(chipTitleAt([long, right], { x: 50, y: 20 })).toBe(long.name);
  expect(chipTitleAt([long, right], { x: 100, y: 20 })).toBe(right.name);
});

it("anchors box chips at the corner and polygon chips at the topmost vertex", () => {
  const box = { x1: 10, y1: 20, x2: 90, y2: 80 };
  expect(boxChipAnchor(box)).toEqual({ x: 10, y: 20, bounds: box });
  const points = [
    { x: 50, y: 40 },
    { x: 30, y: 10 },
    { x: 20, y: 10 },
    { x: 70, y: 60 },
  ];
  expect(polygonChipAnchor(points)).toEqual({
    x: 20,
    y: 10,
    bounds: { x1: 20, y1: 10, x2: 70, y2: 60 },
  });
});
