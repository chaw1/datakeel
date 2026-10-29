import { expect, it, vi } from "vitest";

import { TaskPrefetchCache, warmImage } from "./TaskPrefetchCache";

interface TaskFixture {
  id: string;
  url: string | null;
  revisions: string[];
}

function adapters() {
  const load = vi.fn((id: string): Promise<TaskFixture> =>
    Promise.resolve({ id, url: `/media/${id}`, revisions: [`revision-${id}`] }),
  );
  const warm = vi.fn<(url: string) => Promise<void>>(() => Promise.resolve());
  const cache = new TaskPrefetchCache(load, (task) => task.url, warm);
  return { cache, load, warm };
}

it("prefetches exactly the next two tasks with their existing revisions and media", async () => {
  const { cache, load, warm } = adapters();
  cache.prefetch(["one", "two", "three", "four"], 0);
  await Promise.all([cache.get("two"), cache.get("three")]);
  expect(load.mock.calls.map(([id]) => id)).toEqual(["two", "three"]);
  expect(warm.mock.calls.map(([url]) => url)).toEqual([
    "/media/two",
    "/media/three",
  ]);
  expect(cache.peek("two")).toEqual({
    id: "two",
    url: "/media/two",
    revisions: ["revision-two"],
  });
  expect(cache.peek("four")).toBeNull();
  await cache.get("two");
  expect(load).toHaveBeenCalledTimes(2);
});

it("shares in-flight requests and waits for media to be decoded before marking ready", async () => {
  let decoded!: () => void;
  const warm = vi.fn<(url: string) => Promise<void>>(
    () =>
      new Promise<void>((resolve) => {
        decoded = resolve;
      }),
  );
  const load = vi.fn((id: string) => Promise.resolve({ id, url: "/image" }));
  const cache = new TaskPrefetchCache(load, (task) => task.url, warm);
  const first = cache.get("one");
  expect(cache.get("one")).toBe(first);
  await Promise.resolve();
  expect(cache.peek("one")).toBeNull();
  decoded();
  await first;
  expect(cache.peek("one")).toEqual({ id: "one", url: "/image" });
  expect(load).toHaveBeenCalledTimes(1);
});

it("invalidates stale revisions after writes and retries failed prefetches", async () => {
  const { cache, load } = adapters();
  await cache.get("one");
  cache.invalidate("one");
  load.mockRejectedValueOnce(new Error("Offline"));
  await expect(cache.get("one")).rejects.toThrow("Offline");
  expect(cache.peek("one")).toBeNull();
  await cache.get("one");
  expect(load).toHaveBeenCalledTimes(3);
  const current = { id: "one", url: null, revisions: ["fresh-head"] };
  cache.set("one", current);
  expect(await cache.get("one")).toBe(current);
});

it("keeps a bounded eight-task media/detail cache as the queue advances", async () => {
  const { cache } = adapters();
  for (let step = 0; step < 10; step += 1) await cache.get(String(step));
  expect(cache.peek("0")).toBeNull();
  expect(cache.peek("1")).toBeNull();
  expect(cache.peek("2")?.id).toBe("2");
  expect(cache.peek("9")?.id).toBe("9");
});

it("warms browser images using decode and tolerates invalid media", async () => {
  const decode = vi.fn(() => Promise.reject(new Error("Invalid image")));
  class FakeImage {
    src = "";
    onload = null;
    onerror = null;
    decode = decode;
  }
  vi.stubGlobal("Image", FakeImage);
  await expect(warmImage("/image")).resolves.toBeUndefined();
  expect(decode).toHaveBeenCalledTimes(1);
});

it("clears actor-bound cache entries and prevents stale in-flight loads from restoring them", async () => {
  const { cache, load } = adapters();
  await cache.get("ready");
  let finish!: (value: TaskFixture) => void;
  load.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const previousActor = cache.get("pending");
  cache.clear();
  expect(cache.peek("ready")).toBeNull();
  const currentActor = {
    id: "pending",
    url: null,
    revisions: ["new-actor-head"],
  };
  cache.set("pending", currentActor);
  finish({ id: "pending", url: null, revisions: ["old-actor-head"] });
  await previousActor;
  expect(await cache.get("pending")).toBe(currentActor);
  expect(cache.peek("pending")?.revisions).toEqual(["new-actor-head"]);
});
