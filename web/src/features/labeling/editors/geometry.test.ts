import { describe, expect, it } from "vitest";

import {
  arrowDelta,
  boxFromPoints,
  characterOffset,
  clamp,
  moveBox,
  movePoints,
  parseAttributes,
  resizeBox,
  utf16Offset,
  textareaCharacterOffset,
} from "./geometry";

const box = {
  category: "cat",
  x1: 10,
  y1: 20,
  x2: 40,
  y2: 60,
  attributes: { reviewed: true },
};
describe("natural image coordinates", () => {
  it("normalizes a reverse drag without normalizing pixels", () => {
    expect(
      boxFromPoints({ x: 7800, y: 5900 }, { x: 4200, y: 3100 }, "cat"),
    ).toEqual({
      category: "cat",
      x1: 4200,
      y1: 3100,
      x2: 7800,
      y2: 5900,
      attributes: {},
    });
  });
  it("moves geometry at image boundaries while preserving its size and properties", () => {
    expect(moveBox(box, 100, -100, 100, 100)).toEqual({
      ...box,
      x1: 70,
      y1: 0,
      x2: 100,
      y2: 40,
    });
    expect(box.x1).toBe(10);
    expect(resizeBox(box, -100, 100, 100, 100)).toEqual({
      ...box,
      x2: 11,
      y2: 100,
    });
  });
  it("moves the whole polygon without distorting it at an edge", () => {
    expect(
      movePoints(
        [
          { x: 2, y: 5 },
          { x: 10, y: 5 },
          { x: 8, y: 10 },
        ],
        -20,
        100,
        20,
        20,
      ),
    ).toEqual([
      { x: 0, y: 15 },
      { x: 8, y: 15 },
      { x: 6, y: 20 },
    ]);
    expect(arrowDelta("ArrowLeft", 10)).toEqual({ x: -10, y: 0 });
    expect(arrowDelta("Enter")).toBeNull();
    expect(clamp(-1, 10)).toBe(0);
  });
});
it("validates JSON properties and preserves nested JSON values", () => {
  expect(
    parseAttributes(
      '{"score":0.9,"approved":true,"extra":[null,{"note":"x"}]}',
    ),
  ).toEqual({ score: 0.9, approved: true, extra: [null, { note: "x" }] });
  for (const source of ["null", "[]", "false", "{", '{"score":1e999}'])
    expect(parseAttributes(source)).toBeNull();
});
it("uses Unicode code points for span coordinates rather than UTF-16 offsets", () => {
  expect(characterOffset("A😀中文", 4)).toBe(3);
  expect(utf16Offset("A😀中文", 3)).toBe(4);
});

it("maps textarea CRLF normalization back to original Python character coordinates", () => {
  expect(textareaCharacterOffset("A😀\r\n猫 B", 4)).toBe(4);
  expect(textareaCharacterOffset("A😀\r\n猫 B", 5)).toBe(5);
  expect(textareaCharacterOffset("x\r\ny\r\nz", 4)).toBe(6);
});
