import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../../api/client";

import { AnnotationSession } from "./AnnotationSession";
import { draftKey } from "./draftStorage";
import { useAnnotationSession } from "./useAnnotationSession";

import type {
  AnnotationRecord,
  SavedAnnotation,
  SessionOptions,
} from "./types";

const initial: SavedAnnotation = {
  annotation: { sample_id: "sample-1", annotator_id: "person-1", labels: [] },
  revisionId: null,
};

function changed(step = 1): AnnotationRecord {
  return { ...initial.annotation, labels: [`label-${String(step)}`] };
}

function adapters() {
  return {
    key: "person-1:project-1:task-1",
    initial,
    save: vi.fn<SessionOptions["save"]>((annotation, expected) =>
      Promise.resolve({ annotation, revisionId: `${expected ?? ""}r` }),
    ),
    reload: vi.fn<SessionOptions["reload"]>(() => Promise.resolve(initial)),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it("persists each edit immediately and debounces the latest revision within one second", async () => {
  const options = adapters();
  const { result } = renderHook(() => useAnnotationSession(options));
  act(() => {
    result.current.edit(changed());
  });
  expect(localStorage.getItem(draftKey(options.key))).toContain("label-1");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  act(() => {
    result.current.edit(changed(2));
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(499);
  });
  expect(options.save).not.toHaveBeenCalled();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1);
  });
  expect(options.save).toHaveBeenCalledExactlyOnceWith(changed(2), null);
  expect(result.current.status).toBe("saved");
  expect(localStorage.getItem(draftKey(options.key))).toBeNull();
});

it("recovers offline edits after remount and retries automatically when online", async () => {
  const options = adapters();
  const first = renderHook(() => useAnnotationSession(options));
  act(() => {
    window.dispatchEvent(new Event("offline"));
    first.result.current.edit(changed(7));
  });
  expect(first.result.current.status).toBe("offline");
  await act(async () => {
    expect(await first.result.current.flush()).toBe(false);
    await vi.advanceTimersByTimeAsync(1500);
  });
  expect(options.save).not.toHaveBeenCalled();
  first.unmount();
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
  const second = renderHook(() => useAnnotationSession(options));
  expect(second.result.current.annotation).toEqual(changed(7));
  expect(second.result.current.status).toBe("offline");
  await act(async () => {
    window.dispatchEvent(new Event("online"));
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(options.save).toHaveBeenCalledExactlyOnceWith(changed(7), null);
  expect(second.result.current.status).toBe("saved");
});

it("serializes concurrent flushes and preserves edits made while a save is in flight", async () => {
  const options = adapters();
  const firstWrite = deferred<SavedAnnotation>();
  options.save.mockReturnValueOnce(firstWrite.promise);
  const session = new AnnotationSession(options);
  session.edit(changed());
  const firstFlush = session.flush();
  const secondFlush = session.flush();
  await Promise.resolve();
  expect(options.save).toHaveBeenCalledTimes(1);
  session.edit(changed(2));
  firstWrite.resolve({ annotation: changed(), revisionId: "revision-1" });
  expect(await firstFlush).toBe(true);
  expect(await secondFlush).toBe(true);
  expect(options.save).toHaveBeenCalledTimes(2);
  expect(options.save).toHaveBeenLastCalledWith(changed(2), "revision-1");
  expect(session.getSnapshot().annotation).toEqual(changed(2));
  expect(session.getSnapshot().dirty).toBe(false);
  await vi.advanceTimersByTimeAsync(1000);
  expect(options.save).toHaveBeenCalledTimes(2);
  session.dispose();
});

it("blocks submit and navigation on 409 and overwrites only with an explicitly refreshed head", async () => {
  const options = adapters();
  options.save.mockRejectedValueOnce(new ApiError(409, "Head changed"));
  options.reload.mockResolvedValue({
    annotation: changed(99),
    revisionId: "other-head",
  });
  const session = new AnnotationSession(options);
  session.edit(changed());
  expect(await session.flush()).toBe(false);
  expect(session.getSnapshot().status).toBe("conflict");
  session.edit(changed(2));
  session.setOnline(true);
  await vi.advanceTimersByTimeAsync(2000);
  expect(options.save).toHaveBeenCalledTimes(1);
  expect(await session.flush()).toBe(false);
  expect(await session.overwrite()).toBe(true);
  expect(options.reload).toHaveBeenCalledTimes(1);
  expect(options.save).toHaveBeenLastCalledWith(changed(2), "other-head");
  expect(session.getSnapshot().status).toBe("saved");
  session.dispose();
});

it("preserves a new conflict when another writer changes the refreshed overwrite head", async () => {
  const options = adapters();
  options.save.mockRejectedValue(new ApiError(409, "Head changed again"));
  options.reload.mockResolvedValue({
    annotation: changed(99),
    revisionId: "new-head",
  });
  const session = new AnnotationSession(options);
  session.edit(changed());
  await session.flush();
  expect(await session.overwrite()).toBe(false);
  expect(session.getSnapshot().status).toBe("conflict");
  expect(session.getSnapshot().annotation).toEqual(changed());
  expect(localStorage.getItem(draftKey(options.key))).toContain("label-1");
  session.dispose();
});

it("explicit reload discards local work and installs the freshly read revision", async () => {
  const options = adapters();
  options.save.mockRejectedValueOnce(new ApiError(409, "Head changed"));
  options.reload.mockResolvedValue({
    annotation: changed(99),
    revisionId: "new-head",
  });
  const session = new AnnotationSession(options);
  session.edit(changed());
  await session.flush();
  expect(await session.reload()).toBe(true);
  expect(session.getSnapshot()).toMatchObject({
    annotation: changed(99),
    revisionId: "new-head",
    status: "saved",
    dirty: false,
    canUndo: false,
  });
  expect(localStorage.getItem(draftKey(options.key))).toBeNull();
  session.dispose();
});

it("recognizes a changed remote head after reload without discarding the durable draft", async () => {
  const options = adapters();
  const first = new AnnotationSession(options);
  first.edit(changed());
  first.dispose();
  const next = new AnnotationSession({
    ...options,
    initial: { annotation: changed(99), revisionId: "remote-head" },
  });
  next.start();
  expect(next.getSnapshot().status).toBe("conflict");
  expect(next.getSnapshot().annotation).toEqual(changed());
  await vi.advanceTimersByTimeAsync(1000);
  expect(options.save).not.toHaveBeenCalled();
  next.dispose();
});

it("keeps drafts isolated by actor, project and task identity", () => {
  const options = adapters();
  const first = new AnnotationSession(options);
  first.edit(changed());
  for (const key of [
    "person-2:project-1:task-1",
    "person-1:project-2:task-1",
    "person-1:project-1:task-2",
  ]) {
    const other = new AnnotationSession({ ...options, key });
    expect(other.getSnapshot().annotation).toEqual(initial.annotation);
    other.dispose();
  }
  first.dispose();
});

it("reports storage failures while retaining editable in-memory work", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("Storage quota exceeded", "QuotaExceededError");
  });
  const session = new AnnotationSession(adapters());
  session.edit(changed());
  expect(session.getSnapshot().annotation).toEqual(changed());
  expect(session.getSnapshot().storageError).toContain(
    "Storage quota exceeded",
  );
  session.dispose();
});

it("stops blind retries on permission errors and retries after connectivity recovery", async () => {
  const options = adapters();
  options.save.mockRejectedValueOnce(
    new ApiError(403, "Permission unavailable"),
  );
  const session = new AnnotationSession(options);
  session.start();
  session.edit(changed());
  await vi.advanceTimersByTimeAsync(500);
  expect(session.getSnapshot().status).toBe("error");
  await vi.advanceTimersByTimeAsync(2000);
  expect(options.save).toHaveBeenCalledTimes(1);
  session.setOnline(true);
  await vi.advanceTimersByTimeAsync(0);
  expect(options.save).toHaveBeenCalledTimes(2);
  expect(session.getSnapshot().status).toBe("saved");
  session.dispose();
});

it("does not drop newer edits when an explicit reload response arrives late", async () => {
  const options = adapters();
  const read = deferred<SavedAnnotation>();
  options.reload.mockReturnValueOnce(read.promise);
  const session = new AnnotationSession(options);
  session.edit(changed());
  const reload = session.reload();
  session.edit(changed(2));
  read.resolve({ annotation: changed(99), revisionId: "remote" });
  expect(await reload).toBe(false);
  expect(session.getSnapshot().annotation).toEqual(changed(2));
  session.dispose();
});

it("warns before a refresh with unsaved changes and detaches listeners on unmount", () => {
  const options = adapters();
  const { result, unmount } = renderHook(() => useAnnotationSession(options));
  act(() => {
    result.current.edit(changed());
  });
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
  unmount();
  const later = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(later);
  expect(later.defaultPrevented).toBe(false);
});
