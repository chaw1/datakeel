import { expect, it } from "vitest";

import { AnnotationHistory } from "./history";

import type { AnnotationRecord } from "./types";

const initial: AnnotationRecord = {
  sample_id: "sample",
  annotator_id: "person",
};

const variants = {
  bbox: (step: number): AnnotationRecord => ({
    ...initial,
    image_width: 2000,
    image_height: 1500,
    boxes: [
      {
        category: "box",
        x1: step,
        y1: 10,
        x2: step + 5,
        y2: 30,
        attributes: { step },
      },
    ],
  }),
  polygon: (step: number): AnnotationRecord => ({
    ...initial,
    polygons: [
      {
        category: "polygon",
        points: [
          { x: step, y: 0 },
          { x: step + 5, y: 0 },
          { x: step, y: 10 },
        ],
        attributes: { step },
      },
    ],
  }),
  classification: (step: number): AnnotationRecord => ({
    ...initial,
    labels: [`class-${String(step)}`, "other"],
    attributes: { step, reviewed: true, nested: { value: [1, "two", null] } },
  }),
  span: (step: number): AnnotationRecord => ({
    ...initial,
    text_length: 1000,
    spans: [
      { category: "outer", start: step, end: step + 10 },
      {
        category: "nested",
        start: step + 1,
        end: step + 3,
        attributes: { step },
      },
    ],
  }),
};

it.each(Object.entries(variants))(
  "preserves 200 complete %s edits through undo and redo",
  (_kind, make) => {
    const history = new AnnotationHistory(initial);
    for (let step = 1; step <= 200; step += 1) history.edit(make(step));
    expect(history.current).toEqual(make(200));
    for (let step = 199; step >= 0; step -= 1) {
      expect(history.undo()).toBe(true);
      expect(history.current).toEqual(step === 0 ? initial : make(step));
    }
    expect(history.canUndo).toBe(false);
    expect(history.undo()).toBe(false);
    for (let step = 1; step <= 200; step += 1) {
      expect(history.redo()).toBe(true);
      expect(history.current).toEqual(make(step));
    }
    expect(history.canRedo).toBe(false);
    expect(history.redo()).toBe(false);
  },
);

it("branches history after undo without mutating prior input snapshots", () => {
  const history = new AnnotationHistory(initial);
  const editable = variants.classification(1);
  history.edit(editable);
  editable.labels?.push("changed outside history");
  expect(history.current.labels).toEqual(["class-1", "other"]);
  history.edit(variants.classification(2));
  history.undo();
  expect(history.canRedo).toBe(true);
  history.edit(variants.classification(3));
  expect(history.canRedo).toBe(false);
  history.undo();
  expect(history.current).toEqual(variants.classification(1));
});

it("avoids creating an undo step for an identical annotation", () => {
  const history = new AnnotationHistory(initial);
  expect(history.edit({ ...initial })).toBe(false);
  expect(history.canUndo).toBe(false);
});
