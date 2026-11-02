import { describe, expect, it } from "vitest";

import {
  defaultSegment,
  draftSegment,
  editSegment,
  formatTime,
  visibleSegments,
} from "./segments";

import type { AnnotationSegment } from "./types";

const segment = (start: number, end: number): AnnotationSegment => ({
  category: "a",
  start_ms: start,
  end_ms: end,
  attributes: {},
});

describe("segment geometry", () => {
  it("preserves body duration and enforces 1ms at every edge", () => {
    expect(editSegment(segment(10, 100), "move", -100, 1000)).toMatchObject({
      start_ms: 0,
      end_ms: 90,
    });
    expect(editSegment(segment(10, 100), "start", 100, 1000).start_ms).toBe(99);
    expect(editSegment(segment(10, 100), "end", -100, 1000).end_ms).toBe(11);
    expect(defaultSegment(1000, "a", {}, 1000)).toMatchObject({
      start_ms: 999,
      end_ms: 1000,
    });
  });

  it("normalizes reverse creation and rejects a zero-length release", () => {
    expect(draftSegment(100, 20, "a", {}, 1000)).toMatchObject({
      start_ms: 20,
      end_ms: 100,
    });
    expect(draftSegment(20, 20, "a", {}, 1000)).toBeNull();
  });

  it("sorts only display copies and assigns overlapping swim lanes", () => {
    const records = [segment(100, 200), segment(0, 150), segment(150, 250)];
    const visible = visibleSegments(records, 0, 300);
    expect(visible.map((item) => item.index)).toEqual([1, 0, 2]);
    expect(visible.map((item) => item.lane)).toEqual([0, 1, 0]);
    expect(records.map((item) => item.start_ms)).toEqual([100, 0, 150]);
  });

  it("renders only the visible time window for long media with 500 segments", () => {
    const records = Array.from({ length: 500 }, (_, index) =>
      segment(index * 14_400, index * 14_400 + 1000),
    );
    const visible = visibleSegments(records, 3_600_000, 3_610_000);
    expect(visible).toHaveLength(1);
    expect(visible[0].index).toBe(250);
    expect(records).toHaveLength(500);
  });

  it("formats hours beyond one day without wrapping", () => {
    expect(formatTime(90_061_007)).toBe("25:01:01.007");
  });
});
