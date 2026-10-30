import type { AnnotationBox, Attributes, Point } from "./types";

export function clamp(value: number, maximum: number) {
  return Math.max(0, Math.min(value, maximum));
}
export function boxFromPoints(
  a: Point,
  b: Point,
  category: string,
): AnnotationBox {
  return {
    category,
    x1: Math.min(a.x, b.x),
    y1: Math.min(a.y, b.y),
    x2: Math.max(a.x, b.x),
    y2: Math.max(a.y, b.y),
    attributes: {},
  };
}
export function moveBox(
  box: AnnotationBox,
  dx: number,
  dy: number,
  width: number,
  height: number,
): AnnotationBox {
  const left = clamp(box.x1 + dx, Math.max(0, width - (box.x2 - box.x1)));
  const top = clamp(box.y1 + dy, Math.max(0, height - (box.y2 - box.y1)));
  return {
    ...box,
    x1: left,
    y1: top,
    x2: left + box.x2 - box.x1,
    y2: top + box.y2 - box.y1,
  };
}
export function resizeBox(
  box: AnnotationBox,
  dx: number,
  dy: number,
  width: number,
  height: number,
): AnnotationBox {
  return {
    ...box,
    x2: Math.max(box.x1 + 1, clamp(box.x2 + dx, width)),
    y2: Math.max(box.y1 + 1, clamp(box.y2 + dy, height)),
  };
}
/** Move the top-left corner, keeping at least one source pixel of size. */
export function resizeBoxStart(
  box: AnnotationBox,
  dx: number,
  dy: number,
): AnnotationBox {
  return {
    ...box,
    x1: Math.min(box.x2 - 1, Math.max(0, box.x1 + dx)),
    y1: Math.min(box.y2 - 1, Math.max(0, box.y1 + dy)),
  };
}
/** Arrow keys step one source pixel; Shift steps ten. */
export function keyStep(event: { shiftKey: boolean }) {
  return event.shiftKey ? 10 : 1;
}
export function movePoints(
  points: readonly Point[],
  dx: number,
  dy: number,
  width: number,
  height: number,
): Point[] {
  const xs = points.map((p) => p.x),
    ys = points.map((p) => p.y);
  const x = Math.max(-Math.min(...xs), Math.min(dx, width - Math.max(...xs)));
  const y = Math.max(-Math.min(...ys), Math.min(dy, height - Math.max(...ys)));
  return points.map((p) => ({ x: p.x + x, y: p.y + y }));
}
export function arrowDelta(key: string, step = 1): Point | null {
  return (
    {
      ArrowLeft: { x: -step, y: 0 },
      ArrowRight: { x: step, y: 0 },
      ArrowUp: { x: 0, y: -step },
      ArrowDown: { x: 0, y: step },
    }[key] ?? null
  );
}
/** A source text that only takes a selection, never typed characters. */
export function isSelectableSource(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLTextAreaElement &&
    (target.readOnly || target.getAttribute("aria-readonly") === "true")
  );
}
export function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    !isSelectableSource(target) &&
    (target.isContentEditable ||
      target instanceof HTMLTextAreaElement ||
      target instanceof HTMLSelectElement ||
      (target instanceof HTMLInputElement &&
        !["radio", "checkbox", "button"].includes(target.type)))
  );
}
function isJsonValue(value: unknown): boolean {
  if (value === null || ["string", "boolean"].includes(typeof value))
    return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) return value.every(isJsonValue);
  return typeof value === "object" && Object.values(value).every(isJsonValue);
}
export function parseAttributes(source: string): Attributes | null {
  try {
    const value: unknown = JSON.parse(source);
    return value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      isJsonValue(value)
      ? (value as Attributes)
      : null;
  } catch {
    return null;
  }
}
export function characterOffset(text: string, utf16Offset: number) {
  return Array.from(text.slice(0, utf16Offset)).length;
}
export function utf16Offset(text: string, character: number) {
  return Array.from(text).slice(0, character).join("").length;
}

/** Map textarea-normalized newlines and UTF-16 selection offsets to source characters. */
export function textareaCharacterOffset(text: string, offset: number): number {
  const characters = Array.from(text);
  let displayed = 0;
  let source = 0;
  while (source < characters.length && displayed < offset) {
    const character = characters.at(source);
    if (character === "\r" && characters.at(source + 1) === "\n") {
      source += 2;
      displayed += 1;
    } else if (character !== undefined) {
      source += 1;
      displayed += character.length;
    }
  }
  return source;
}
