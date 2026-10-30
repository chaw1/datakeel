import { ApiError } from "../../../api/client";

import { readDraft, writeDraft } from "./draftStorage";
import { AnnotationHistory, sameAnnotation } from "./history";

import type {
  AnnotationRecord,
  SavedAnnotation,
  SessionOptions,
  SessionSnapshot,
} from "./types";

const SAVE_DELAY_MS = 500;

function message(reason: unknown) {
  return reason instanceof Error ? reason.message : String(reason);
}

function retryable(reason: unknown) {
  return (
    reason instanceof TypeError ||
    (reason instanceof ApiError &&
      [408, 429, 502, 503, 504].includes(reason.status))
  );
}

/** Serialize revision writes while retaining edits made during a pending save. */
export class AnnotationSession {
  private options: SessionOptions;
  private history: AnnotationHistory;
  private base: SavedAnnotation;
  private online: boolean;
  private conflict = false;
  private resolving = false;
  private disposed = false;
  private generation = 0;
  private retryAttempt = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private inFlight: Promise<boolean> | null = null;
  private listeners = new Set<() => void>();
  private snapshot: SessionSnapshot;

  constructor(options: SessionOptions) {
    this.options = options;
    this.base = structuredClone(options.initial);
    this.history = new AnnotationHistory(options.initial.annotation);
    this.online = navigator.onLine;
    this.snapshot = {
      annotation: this.history.current,
      revisionId: this.base.revisionId,
      status: "saved",
      dirty: false,
      canUndo: false,
      canRedo: false,
      error: "",
      storageError: "",
    };
    this.restore();
  }

  getSnapshot = () => this.snapshot;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  setAdapters(
    save: SessionOptions["save"],
    reload: SessionOptions["reload"],
    validate?: SessionOptions["validate"],
  ) {
    this.options = { ...this.options, save, reload, validate };
  }

  start() {
    this.disposed = false;
    this.schedule();
  }

  dispose() {
    this.disposed = true;
    this.clearTimer();
  }

  edit = (annotation: AnnotationRecord) => {
    if (this.history.edit(annotation)) this.changed();
  };

  undo = () => {
    if (this.history.undo()) this.changed();
  };

  redo = () => {
    if (this.history.redo()) this.changed();
  };

  setOnline = (online: boolean) => {
    this.online = online;
    if (online) this.retryAttempt = 0;
    this.publish({ status: this.status() });
    if (online) this.schedule(0);
    else this.clearTimer();
  };

  /** Resolve false to keep navigation/submission blocked until data is saved. */
  flush = async (): Promise<boolean> => {
    this.clearTimer();
    if (this.resolving || this.conflict) return false;
    if (this.holdBack()) return false;
    while (this.dirty || this.inFlight) {
      if (!this.online) return false;
      const saved = await (this.inFlight ?? this.saveOnce());
      if (!saved) return false;
    }
    return true;
  };

  /** Discard a conflicted local draft only after an explicit human choice. */
  reload = async (): Promise<boolean> => {
    if (this.resolving || this.inFlight || !this.online) return false;
    this.resolving = true;
    this.clearTimer();
    const generation = this.generation;
    try {
      const latest = await this.options.reload();
      if (generation !== this.generation) return false;
      this.base = structuredClone(latest);
      this.history = new AnnotationHistory(latest.annotation);
      this.conflict = false;
      this.persist();
      this.publish({ status: "saved", error: "" });
      return true;
    } catch (reason) {
      this.publish({ error: message(reason), status: this.status("error") });
      return false;
    } finally {
      this.resolving = false;
      this.schedule();
    }
  };

  /** Reload the head first; another concurrent write still raises a new conflict. */
  overwrite = async (): Promise<boolean> => {
    if (this.resolving || this.inFlight || !this.online) return false;
    this.resolving = true;
    this.clearTimer();
    try {
      this.base = structuredClone(await this.options.reload());
      this.conflict = false;
      this.persist();
      this.publish({ status: this.status(), error: "" });
    } catch (reason) {
      this.publish({ error: message(reason), status: this.status("error") });
      return false;
    } finally {
      this.resolving = false;
    }
    return this.flush();
  };

  private get dirty() {
    return !sameAnnotation(this.history.current, this.base.annotation);
  }

  /** Keep an incomplete edit local (the draft is persisted) until it can pass validation. */
  private holdBack() {
    const problem = this.dirty
      ? (this.options.validate?.(this.history.current) ?? "")
      : "";
    if (problem) this.publish({ status: "incomplete", error: problem });
    else if (this.snapshot.status === "incomplete")
      this.publish({ status: this.status(), error: "" });
    return !!problem;
  }

  private status(fallback: SessionSnapshot["status"] = "pending") {
    if (this.conflict) return "conflict";
    if (!this.dirty) return "saved";
    if (!this.online) return "offline";
    if (this.inFlight) return "saving";
    return fallback;
  }

  private restore() {
    try {
      const draft = readDraft(this.options.key, this.base.annotation);
      if (draft && !sameAnnotation(draft.annotation, draft.base.annotation)) {
        this.conflict = draft.base.revisionId !== this.base.revisionId;
        this.base = draft.base;
        this.history = new AnnotationHistory(draft.annotation);
        this.publish({ status: this.status() });
      }
    } catch (reason) {
      this.publish({ storageError: message(reason) });
    }
  }

  private changed() {
    this.generation += 1;
    this.retryAttempt = 0;
    this.persist();
    this.publish({ status: this.status(), error: "" });
    this.schedule();
  }

  private persist() {
    try {
      writeDraft(this.options.key, this.base, this.history.current, this.dirty);
      this.publish({ storageError: "" });
    } catch (reason) {
      this.publish({ storageError: message(reason) });
    }
  }

  private publish(update: Partial<SessionSnapshot>) {
    this.snapshot = {
      ...this.snapshot,
      annotation: this.history.current,
      revisionId: this.base.revisionId,
      dirty: this.dirty,
      canUndo: this.history.canUndo,
      canRedo: this.history.canRedo,
      ...update,
    };
    this.listeners.forEach((listener) => {
      listener();
    });
  }

  private clearTimer() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  private schedule(delay = SAVE_DELAY_MS) {
    this.clearTimer();
    if (
      this.disposed ||
      this.resolving ||
      !this.dirty ||
      !this.online ||
      this.conflict ||
      this.inFlight ||
      this.holdBack()
    )
      return;
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.saveOnce();
    }, delay);
  }

  private saveOnce(): Promise<boolean> {
    if (this.inFlight) return this.inFlight;
    this.clearTimer();
    const submitted = structuredClone(this.history.current);
    const revisionId = this.base.revisionId;
    let retryDelay: number | null = null;
    this.publish({ status: "saving", error: "" });
    const operation = Promise.resolve()
      .then(() => this.options.save(submitted, revisionId))
      .then((saved) => {
        this.retryAttempt = 0;
        this.base = structuredClone(saved);
        if (sameAnnotation(submitted, this.history.current))
          this.history.replaceCurrent(saved.annotation);
        this.persist();
        this.publish({
          status: !this.dirty ? "saved" : this.online ? "pending" : "offline",
          error: "",
        });
        return true;
      })
      .catch((reason: unknown) => {
        this.conflict = reason instanceof ApiError && reason.status === 409;
        if (retryable(reason)) {
          retryDelay = Math.min(1000 * 2 ** this.retryAttempt, 5000);
          this.retryAttempt = Math.min(this.retryAttempt + 1, 3);
        }
        this.persist();
        this.publish({
          error: message(reason),
          status: this.conflict
            ? "conflict"
            : this.online
              ? "error"
              : "offline",
        });
        return false;
      })
      .finally(() => {
        this.inFlight = null;
        if (retryDelay !== null) this.schedule(retryDelay);
        else if (this.snapshot.status !== "error") this.schedule();
      });
    this.inFlight = operation;
    return operation;
  }
}
