import type { components } from "../../../api/generated";

export type AnnotationRecord = components["schemas"]["AnnotationRecord"];

export interface SavedAnnotation {
  annotation: AnnotationRecord;
  revisionId: string | null;
}

export interface SessionOptions {
  /** Include actor, project and task identity; remount the hook when this changes. */
  key: string;
  initial: SavedAnnotation;
  save: (
    annotation: AnnotationRecord,
    expectedRevisionId: string | null,
  ) => Promise<SavedAnnotation>;
  reload: () => Promise<SavedAnnotation>;
}

export type SaveStatus =
  "saved" | "pending" | "saving" | "offline" | "conflict" | "error";

export interface SessionSnapshot {
  annotation: AnnotationRecord;
  revisionId: string | null;
  status: SaveStatus;
  dirty: boolean;
  canUndo: boolean;
  canRedo: boolean;
  error: string;
  storageError: string;
}
