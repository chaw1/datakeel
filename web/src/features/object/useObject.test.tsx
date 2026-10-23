import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { loadObject } from "../../api/objects";

import { objectData } from "./testFixtures";
import { useObject } from "./useObject";

import type { ObjectTarget } from "./navigation";
import type { ObjectData } from "../../api/objects";

vi.mock("../../api/objects", () => ({ loadObject: vi.fn() }));
beforeEach(() => {
  vi.mocked(loadObject).mockReset();
});
function deferred() {
  let resolve!: (value: ObjectData) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<ObjectData>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

it("keeps the mounted object's content throughout reload and a transient read error", async () => {
  const pending = deferred();
  vi.mocked(loadObject)
    .mockResolvedValueOnce(objectData)
    .mockReturnValueOnce(pending.promise);
  const { result } = renderHook(() => useObject(objectData.target));
  await waitFor(() => {
    expect(result.current.value).toBe(objectData);
  });
  act(() => {
    result.current.reload();
  });
  expect(result.current.loading).toBe(true);
  expect(result.current.value).toBe(objectData);
  await act(async () => {
    pending.reject(new Error("temporary read failure"));
    await pending.promise.catch(() => undefined);
  });
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toBe("temporary read failure");
  expect(result.current.value).toBe(objectData);
  const fresh = { ...objectData, name: "Refreshed collection" };
  vi.mocked(loadObject).mockResolvedValueOnce(fresh);
  act(() => {
    result.current.reload();
  });
  await waitFor(() => {
    expect(result.current.value).toBe(fresh);
  });
  expect(result.current.error).toBe("");
});

it.each([
  { kind: "dataset", id: "another-dataset" },
  { kind: "file", id: objectData.target.id },
  { ...objectData.target, datasetId: "other-context" },
  { ...objectData.target, versionId: "other-version" },
] satisfies ObjectTarget[])(
  "never displays old data after switching identity/context %j",
  async (target) => {
    const pending = deferred();
    vi.mocked(loadObject)
      .mockResolvedValueOnce(objectData)
      .mockReturnValueOnce(pending.promise);
    const { result, rerender } = renderHook(
      ({ selected }: { selected: ObjectTarget }) => useObject(selected),
      { initialProps: { selected: objectData.target } },
    );
    await waitFor(() => {
      expect(result.current.value).toBe(objectData);
    });
    rerender({ selected: target });
    expect(result.current.value).toBeNull();
    expect(result.current.loading).toBe(true);
    await act(async () => {
      pending.reject(new Error("new object unavailable"));
      await pending.promise.catch(() => undefined);
    });
    expect(result.current.value).toBeNull();
    expect(result.current.error).toBe("new object unavailable");
  },
);

it("ignores a late reload from an object that has already been left", async () => {
  const stale = deferred();
  const next = {
    ...objectData,
    target: { kind: "dataset", id: "next" } as const,
    name: "Next",
  };
  vi.mocked(loadObject)
    .mockResolvedValueOnce(objectData)
    .mockReturnValueOnce(stale.promise)
    .mockResolvedValueOnce(next);
  const { result, rerender } = renderHook(
    ({ selected }: { selected: ObjectTarget }) => useObject(selected),
    { initialProps: { selected: objectData.target } },
  );
  await waitFor(() => {
    expect(result.current.value).toBe(objectData);
  });
  act(() => {
    result.current.reload();
  });
  rerender({ selected: next.target });
  await waitFor(() => {
    expect(result.current.value).toBe(next);
  });
  await act(async () => {
    stale.resolve({ ...objectData, name: "Stale" });
    await stale.promise;
  });
  expect(result.current.value).toBe(next);
});
