import type { AnnotationRecord, SavedAnnotation } from "./types";

interface DurableDraft {
  version: 1;
  base: SavedAnnotation;
  annotation: AnnotationRecord;
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function annotation(value: unknown, identity: AnnotationRecord) {
  return (
    record(value) &&
    value.sample_id === identity.sample_id &&
    value.annotator_id === identity.annotator_id
  );
}

function isDraft(
  value: unknown,
  identity: AnnotationRecord,
): value is DurableDraft {
  return (
    record(value) &&
    value.version === 1 &&
    record(value.base) &&
    (value.base.revisionId === null ||
      typeof value.base.revisionId === "string") &&
    annotation(value.base.annotation, identity) &&
    annotation(value.annotation, identity)
  );
}

export function draftKey(key: string) {
  return `datakeel.annotation-draft:${key}`;
}

export function readDraft(key: string, identity: AnnotationRecord) {
  const stored = localStorage.getItem(draftKey(key));
  if (stored === null) return null;
  const value: unknown = JSON.parse(stored);
  if (!isDraft(value, identity))
    throw new Error("Invalid local annotation draft");
  return value;
}

export function writeDraft(
  key: string,
  base: SavedAnnotation,
  current: AnnotationRecord,
  dirty: boolean,
) {
  if (!dirty) {
    localStorage.removeItem(draftKey(key));
    return;
  }
  const draft: DurableDraft = { version: 1, base, annotation: current };
  localStorage.setItem(draftKey(key), JSON.stringify(draft));
}
