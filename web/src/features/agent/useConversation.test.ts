import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { streamMessage, streamResume } from "../../api/agent";
import { get } from "../../api/client";
import { agentEvent, conversation } from "../../test/agentFixtures";

import { useConversation } from "./useConversation";

vi.mock("../../api/agent", () => ({
  streamMessage: vi.fn(),
  streamResume: vi.fn(),
}));
vi.mock("../../api/client", () => ({ get: vi.fn() }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  vi.mocked(get).mockReset().mockResolvedValue(conversation);
  vi.mocked(streamMessage).mockReset().mockResolvedValue(undefined);
  vi.mocked(streamResume).mockReset().mockResolvedValue(undefined);
});

it("sends explicit modes and prevents overlapping requests before the next render", async () => {
  const pending = deferred<undefined>();
  vi.mocked(streamMessage).mockReturnValue(pending.promise);
  const { result } = renderHook(() => useConversation(conversation.id));
  await waitFor(() => {
    expect(result.current.value).toEqual(conversation);
  });
  let completion: Promise<void> | undefined;
  act(() => {
    completion = result.current.send("Investigate", undefined, "agent");
    void result.current.send("Duplicate");
  });
  expect(streamMessage).toHaveBeenCalledTimes(1);
  expect(streamMessage).toHaveBeenCalledWith(
    conversation.id,
    expect.objectContaining({ content: "Investigate", mode: "agent" }),
    expect.any(Function),
    expect.any(AbortSignal),
  );
  act(() => {
    vi.mocked(streamMessage).mock.calls[0][2](
      agentEvent("text", { text: "live" }),
    );
  });
  expect(result.current.live.events).toHaveLength(1);
  await act(async () => {
    pending.resolve(undefined);
    await completion;
  });
  expect(result.current.live.running).toBe(false);
  expect(result.current.live.events).toHaveLength(0);
  expect(get).toHaveBeenCalledTimes(2);
});

it("resumes without a synthetic user message and uses a fresh idempotency key", async () => {
  const pending = deferred<undefined>();
  const { result } = renderHook(() => useConversation(conversation.id));
  await waitFor(() => {
    expect(result.current.value).toEqual(conversation);
  });
  await act(() => result.current.send("Prepare a plan"));
  vi.mocked(streamResume).mockReturnValue(pending.promise);
  let completion: Promise<void> | undefined;
  act(() => {
    completion = result.current.resume("plan-1");
  });
  const sent = vi.mocked(streamMessage).mock.calls[0][1];
  const resumed = vi.mocked(streamResume).mock.calls[0][1];
  expect(sent.mode).toBe("auto");
  expect(resumed.plan_id).toBe("plan-1");
  expect(resumed.idempotency_key).not.toBe(sent.idempotency_key);
  expect(result.current.live.content).toBe("");
  expect(result.current.live.running).toBe(true);
  act(() => {
    vi.mocked(streamResume).mock.calls[0][2](
      agentEvent("text", { text: "continued" }),
    );
  });
  expect(result.current.live.events[0].text).toBe("continued");
  await act(async () => {
    pending.resolve(undefined);
    await completion;
  });
  expect(result.current.live.running).toBe(false);
  expect(get).toHaveBeenCalledTimes(3);
});

it("surfaces resume refusals after reloading persisted state", async () => {
  vi.mocked(streamResume).mockRejectedValue(
    new Error("409 Plan is not approved"),
  );
  const { result } = renderHook(() => useConversation(conversation.id));
  await waitFor(() => {
    expect(result.current.value).toEqual(conversation);
  });
  await act(() => result.current.resume("plan-1"));
  expect(result.current.live.error).toBe("409 Plan is not approved");
  expect(result.current.live.running).toBe(false);
  expect(get).toHaveBeenCalledTimes(2);
  act(() => {
    result.current.reload();
  });
  await waitFor(() => {
    expect(result.current.loading).toBe(false);
  });
  expect(result.current.live.error).toBe("");
});

it("stops immediately, reloads the interrupted boundary, and ignores late stream events", async () => {
  const pending = deferred<undefined>();
  const saved = {
    ...conversation,
    events: [agentEvent("stopped", { stop_reason: "interrupted" })],
  };
  vi.mocked(streamMessage).mockReturnValue(pending.promise);
  const { result } = renderHook(() => useConversation(conversation.id));
  await waitFor(() => {
    expect(result.current.value).toEqual(conversation);
  });
  let completion: Promise<void> | undefined;
  act(() => {
    completion = result.current.send("Investigate");
  });
  const [, , receive, signal] = vi.mocked(streamMessage).mock.calls[0];
  vi.mocked(get).mockResolvedValue(saved);
  await act(() => result.current.stop());
  expect(signal.aborted).toBe(true);
  expect(result.current.live.running).toBe(false);
  expect(result.current.value).toEqual(saved);
  await act(async () => {
    receive(agentEvent("text", { text: "stale" }));
    pending.resolve(undefined);
    await completion;
  });
  expect(result.current.live.events).toHaveLength(0);
  expect(get).toHaveBeenCalledTimes(2);
});

it("keeps a stopped refresh and old conversation stream from replacing the active session", async () => {
  const pending = deferred<undefined>();
  const staleLoad = deferred<typeof conversation>();
  vi.mocked(streamMessage).mockReturnValue(pending.promise);
  const { result, rerender } = renderHook(({ id }) => useConversation(id), {
    initialProps: { id: conversation.id },
  });
  await waitFor(() => {
    expect(result.current.value).toEqual(conversation);
  });
  let completion: Promise<void> | undefined;
  act(() => {
    completion = result.current.send("Old request");
  });
  vi.mocked(get).mockReturnValueOnce(staleLoad.promise);
  let stopped: Promise<void> | undefined;
  act(() => {
    stopped = result.current.stop();
  });
  const next = { ...conversation, id: "conversation-2" };
  vi.mocked(get).mockResolvedValue(next);
  rerender({ id: next.id });
  await waitFor(() => {
    expect(result.current.value).toEqual(next);
  });
  await act(async () => {
    vi.mocked(streamMessage).mock.calls[0][2](
      agentEvent("text", { text: "stale" }),
    );
    staleLoad.resolve(conversation);
    pending.resolve(undefined);
    await Promise.all([completion, stopped]);
  });
  expect(result.current.value).toEqual(next);
  expect(result.current.live.events).toHaveLength(0);
});

it("does not restore an aborted live turn when returning to the same conversation", async () => {
  const pending = deferred<undefined>();
  vi.mocked(streamMessage).mockReturnValue(pending.promise);
  const { result, rerender } = renderHook(({ id }) => useConversation(id), {
    initialProps: { id: conversation.id },
  });
  await waitFor(() => {
    expect(result.current.value).toEqual(conversation);
  });
  let completion: Promise<void> | undefined;
  act(() => {
    completion = result.current.send("Old request");
  });
  expect(result.current.live.running).toBe(true);
  rerender({ id: "" });
  rerender({ id: conversation.id });
  await waitFor(() => {
    expect(result.current.live.running).toBe(false);
    expect(result.current.live.content).toBe("");
  });
  expect(vi.mocked(streamMessage).mock.calls[0][3].aborted).toBe(true);
  await act(async () => {
    pending.resolve(undefined);
    await completion;
  });
  expect(result.current.live.running).toBe(false);
});

it("keeps an initial snapshot from duplicating the active streamed turn", async () => {
  const initial = deferred<typeof conversation>();
  const pending = deferred<undefined>();
  const text = agentEvent("text", { text: "Investigating" });
  const saved: typeof conversation = {
    ...conversation,
    messages: [{ role: "user", content: "Investigate" }],
    events: [text],
  };
  vi.mocked(get).mockReturnValueOnce(initial.promise).mockResolvedValue(saved);
  vi.mocked(streamMessage).mockReturnValue(pending.promise);
  const { result } = renderHook(() => useConversation(conversation.id));
  let completion: Promise<void> | undefined;
  act(() => {
    completion = result.current.send("Investigate");
    vi.mocked(streamMessage).mock.calls[0][2](text);
  });
  await act(async () => {
    initial.resolve(saved);
    await initial.promise;
  });
  expect(result.current.value).toBeNull();
  expect(result.current.live.content).toBe("Investigate");
  expect(result.current.live.events).toEqual([text]);
  await act(async () => {
    pending.resolve(undefined);
    await completion;
  });
  expect(result.current.value).toEqual(saved);
  expect(result.current.live.events).toHaveLength(0);
});
