import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { useAnnotationSession } from "./useAnnotationSession";

import type { SessionOptions } from "./types";

it("uses fresh save and reload adapters after permission or locale context changes", async () => {
  const initial = {
    annotation: { sample_id: "sample", annotator_id: "person", labels: [] },
    revisionId: null,
  };
  const originalSave = vi.fn<SessionOptions["save"]>(() =>
    Promise.resolve(initial),
  );
  const originalReload = vi.fn<SessionOptions["reload"]>(() =>
    Promise.resolve(initial),
  );
  const changed = { ...initial.annotation, labels: ["reviewed"] };
  const latest = { annotation: changed, revisionId: "new-head" };
  const newSave = vi.fn<SessionOptions["save"]>(() => Promise.resolve(latest));
  const newReload = vi.fn<SessionOptions["reload"]>(() =>
    Promise.resolve(latest),
  );
  const { result, rerender } = renderHook(
    (adapters: Pick<SessionOptions, "save" | "reload">) =>
      useAnnotationSession({
        key: "person:project:sample",
        initial,
        ...adapters,
      }),
    { initialProps: { save: originalSave, reload: originalReload } },
  );
  rerender({ save: newSave, reload: newReload });
  await act(async () => {
    result.current.edit(changed);
    expect(await result.current.flush()).toBe(true);
  });
  expect(newSave).toHaveBeenCalledExactlyOnceWith(changed, null);
  expect(originalSave).not.toHaveBeenCalled();
  await act(async () => {
    expect(await result.current.reload()).toBe(true);
  });
  expect(newReload).toHaveBeenCalledTimes(1);
  expect(originalReload).not.toHaveBeenCalled();
});
