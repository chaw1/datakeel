import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../../api/client";

import { AnnotationSession } from "./AnnotationSession";

import type { SessionOptions } from "./types";

function setup() {
  const initial = {
    annotation: { sample_id: "sample", annotator_id: "person", labels: [] },
    revisionId: null,
  };
  const save = vi.fn<SessionOptions["save"]>((annotation) =>
    Promise.resolve({ annotation, revisionId: "saved" }),
  );
  const session = new AnnotationSession({
    key: "retry-test",
    initial,
    save,
    reload: () => Promise.resolve(initial),
  });
  session.start();
  session.edit({ ...initial.annotation, labels: ["edited"] });
  return { save, session };
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

it.each([
  new TypeError("Fetch failed"),
  ...[408, 429, 502, 503, 504].map(
    (status) => new ApiError(status, "Temporarily unavailable"),
  ),
])(
  "retries transient failure %s without needing a browser online event",
  async (reason) => {
    const { save, session } = setup();
    save.mockRejectedValueOnce(reason);
    await vi.advanceTimersByTimeAsync(500);
    expect(session.getSnapshot().status).toBe("error");
    expect(save).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(999);
    expect(save).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(save).toHaveBeenCalledTimes(2);
    expect(session.getSnapshot()).toMatchObject({
      status: "saved",
      dirty: false,
    });
    session.dispose();
  },
);

it("caps retry backoff at five seconds and stops retrying after unmount", async () => {
  const { save, session } = setup();
  save.mockRejectedValue(new TypeError("Connection unavailable"));
  await vi.advanceTimersByTimeAsync(500 + 1000 + 2000 + 4000 + 5000 + 5000);
  expect(save).toHaveBeenCalledTimes(6);
  expect(session.getSnapshot().dirty).toBe(true);
  session.dispose();
  await vi.advanceTimersByTimeAsync(20_000);
  expect(save).toHaveBeenCalledTimes(6);
});

it.each([400, 401, 403, 409, 422])(
  "keeps failure %s for explicit recovery instead of blind retries",
  async (status) => {
    const { save, session } = setup();
    save.mockRejectedValue(new ApiError(status, "Explicit recovery required"));
    await vi.advanceTimersByTimeAsync(20_000);
    expect(save).toHaveBeenCalledTimes(1);
    expect(session.getSnapshot().status).toBe(
      status === 409 ? "conflict" : "error",
    );
    session.dispose();
  },
);
