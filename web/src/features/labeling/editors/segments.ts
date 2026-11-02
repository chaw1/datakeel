import type { AnnotationSegment, Attributes } from "./types";

export type SegmentEditMode = "move" | "start" | "end";
export interface PositionedSegment {
  segment: AnnotationSegment;
  index: number;
  lane: number;
}

export function clampTime(value: number, duration: number) {
  return Math.max(0, Math.min(Math.round(value), duration));
}

/** Create a normalized pointer range; a zero-length release creates nothing. */
export function draftSegment(
  first: number,
  second: number,
  category: string,
  attributes: Attributes,
  duration: number,
): AnnotationSegment | null {
  const startMs = clampTime(Math.min(first, second), duration);
  const endMs = clampTime(Math.max(first, second), duration);
  if (startMs >= endMs) return null;
  return {
    category,
    start_ms: startMs,
    end_ms: endMs,
    attributes,
  };
}

export function defaultSegment(
  playhead: number,
  category: string,
  attributes: Attributes,
  duration: number,
): AnnotationSegment {
  const startMs = clampTime(playhead, Math.max(0, duration - 1));
  return {
    category,
    start_ms: startMs,
    end_ms: Math.min(duration, startMs + 1000),
    attributes,
  };
}

/** Move a body without changing its duration, or resize one edge to at least 1ms. */
export function editSegment(
  segment: AnnotationSegment,
  mode: SegmentEditMode,
  delta: number,
  duration: number,
): AnnotationSegment {
  const body = segment.end_ms - segment.start_ms;
  if (mode === "move") {
    const startMs = clampTime(segment.start_ms + delta, duration - body);
    return { ...segment, start_ms: startMs, end_ms: startMs + body };
  }
  if (mode === "start") {
    return {
      ...segment,
      start_ms: Math.max(
        0,
        Math.min(
          segment.end_ms - 1,
          clampTime(segment.start_ms + delta, duration),
        ),
      ),
    };
  }
  return {
    ...segment,
    end_ms: Math.max(
      segment.start_ms + 1,
      clampTime(segment.end_ms + delta, duration),
    ),
  };
}

/** Sort only a display copy and assign overlap lanes without changing record order. */
export function visibleSegments(
  segments: readonly AnnotationSegment[],
  windowStart: number,
  windowEnd: number,
): PositionedSegment[] {
  const visible = segments
    .map((segment, index) => ({ segment, index }))
    .filter(
      ({ segment }) =>
        segment.end_ms > windowStart && segment.start_ms < windowEnd,
    )
    .sort(
      (a, b) =>
        a.segment.start_ms - b.segment.start_ms ||
        a.segment.end_ms - b.segment.end_ms ||
        a.index - b.index,
    );
  const laneEnds: number[] = [];
  return visible.map((item) => {
    let lane = laneEnds.findIndex((end) => end <= item.segment.start_ms);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = item.segment.end_ms;
    return { ...item, lane };
  });
}

export function formatTime(milliseconds: number) {
  const value = Math.max(0, Math.round(milliseconds));
  const hours = Math.floor(value / 3_600_000);
  const minutes = Math.floor(value / 60_000) % 60;
  const seconds = Math.floor(value / 1000) % 60;
  const ms = value % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
}
