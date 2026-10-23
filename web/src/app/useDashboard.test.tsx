import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../test/actionFixtures";
import { dataset, task } from "../test/fixtures";

import { useDashboard } from "./useDashboard";

import type { DashboardSnapshot } from "./useDashboard";

const endpoints: Record<string, keyof DashboardSnapshot> = {
  "/api/datasets?include=quality": "datasets",
  "/api/approvals": "approvals",
  "/api/tasks": "tasks",
  "/api/actions/runs": "actions",
};

function snapshot(): DashboardSnapshot {
  return {
    datasets: [
      { ...dataset, id: "below", quality_score: 59 },
      { ...dataset, id: "boundary", quality_score: 60 },
      { ...dataset, id: "unmeasured", quality_score: null },
    ],
    approvals: [actionPlan, { ...actionPlan, id: "plan-2" }],
    tasks: [{ ...task, state: "RUNNING", progress: 50 }, task],
    actions: [actionRun],
  };
}

function serve(read: () => DashboardSnapshot) {
  const fetch = vi.fn((path: string, init: RequestInit) => {
    expect(init.method).toBe("GET");
    const key = endpoints[path];
    expect(key).toBeDefined();
    return Promise.resolve(new Response(JSON.stringify(read()[key])));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("publishes one complete snapshot only after all four real HTTP responses resolve", async () => {
  const data = snapshot();
  let finishTasks: ((response: Response) => void) | undefined;
  const tasks = new Promise<Response>((resolve) => {
    finishTasks = resolve;
  });
  const fetch = vi.fn((path: string, init: RequestInit) => {
    expect(init.method).toBe("GET");
    return path === "/api/tasks"
      ? tasks
      : Promise.resolve(new Response(JSON.stringify(data[endpoints[path]])));
  });
  vi.stubGlobal("fetch", fetch);
  const { result } = renderHook(() => useDashboard());
  await flush();
  expect(result.current.loading).toBe(true);
  expect(result.current.value).toEqual({
    datasets: [],
    approvals: [],
    tasks: [],
    actions: [],
  });
  expect(fetch.mock.calls.map(([path]) => path).sort()).toEqual(
    Object.keys(endpoints).sort(),
  );
  finishTasks?.(new Response(JSON.stringify(data.tasks)));
  await flush();
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toBe("");
  expect(result.current.value).toEqual(data);
});

it("polls every ten seconds and stops requesting after unmount", async () => {
  let data = snapshot();
  const fetch = serve(() => data);
  const { result, unmount } = renderHook(() => useDashboard());
  await flush();
  expect(fetch).toHaveBeenCalledTimes(4);
  data = { ...data, approvals: [], tasks: [{ ...task, progress: 100 }] };
  await act(async () => {
    await vi.advanceTimersByTimeAsync(9_999);
  });
  expect(fetch).toHaveBeenCalledTimes(4);
  expect(result.current.value.approvals).toHaveLength(2);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1);
  });
  expect(fetch).toHaveBeenCalledTimes(8);
  expect(result.current.value).toEqual(data);
  unmount();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(20_000);
  });
  expect(fetch).toHaveBeenCalledTimes(8);
});

it("refreshes approval count immediately on reload without advancing the clock", async () => {
  let data = snapshot();
  const fetch = serve(() => data);
  const { result } = renderHook(() => useDashboard());
  await flush();
  expect(result.current.value.approvals).toHaveLength(2);
  const before = Date.now();
  data = { ...data, approvals: [actionPlan] };
  act(() => {
    result.current.reload();
  });
  await flush();
  expect(Date.now()).toBe(before);
  expect(result.current.value.approvals).toHaveLength(1);
  expect(fetch).toHaveBeenCalledTimes(8);
  data = { ...data, approvals: [] };
  act(() => {
    result.current.reload();
  });
  await flush();
  expect(Date.now()).toBe(before);
  expect(result.current.value.approvals).toHaveLength(0);
  expect(fetch).toHaveBeenCalledTimes(12);
});

it("retains quality scores 59, 60 and null exactly without modifying source facts", async () => {
  const data = snapshot();
  const original = JSON.stringify(data);
  serve(() => data);
  const { result } = renderHook(() => useDashboard());
  await flush();
  expect(
    result.current.value.datasets.map((item) => item.quality_score),
  ).toEqual([59, 60, null]);
  expect(result.current.value.datasets.map((item) => item.file_count)).toEqual([
    dataset.file_count,
    dataset.file_count,
    dataset.file_count,
  ]);
  expect(JSON.stringify(data)).toBe(original);
});
