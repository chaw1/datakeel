import type { AnnotationRecord } from "./types";

export function sameAnnotation(a: AnnotationRecord, b: AnnotationRecord) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Keep every edit for this mounted task, including geometry and attributes. */
export class AnnotationHistory {
  private entries: AnnotationRecord[];
  private cursor = 0;

  constructor(initial: AnnotationRecord) {
    this.entries = [structuredClone(initial)];
  }

  get current() {
    return this.entries[this.cursor];
  }

  get canUndo() {
    return this.cursor > 0;
  }

  get canRedo() {
    return this.cursor + 1 < this.entries.length;
  }

  edit(annotation: AnnotationRecord) {
    if (sameAnnotation(this.current, annotation)) return false;
    this.entries = this.entries.slice(0, this.cursor + 1);
    this.entries.push(structuredClone(annotation));
    this.cursor += 1;
    return true;
  }

  undo() {
    if (!this.canUndo) return false;
    this.cursor -= 1;
    return true;
  }

  redo() {
    if (!this.canRedo) return false;
    this.cursor += 1;
    return true;
  }

  replaceCurrent(annotation: AnnotationRecord) {
    this.entries[this.cursor] = structuredClone(annotation);
  }
}
