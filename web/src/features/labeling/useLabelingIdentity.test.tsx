import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import {
  getProjectWorkbench,
  getTaskWorkbench,
  getWorkbench,
} from "../../api/production";
import {
  labelingIndex,
  labelingProject,
  labelingTask,
} from "../../test/labelingFixtures";

import { readWorkspaceSnapshot } from "./session/workspaceSnapshot";
import { useLabelingWorkspace } from "./useLabelingWorkspace";

import type {
  ProjectWorkbench,
  TaskWorkbench,
  WorkbenchIndex,
} from "../../api/production";

vi.mock("../../api/production", () => ({
  getWorkbench: vi.fn(),
  getProjectWorkbench: vi.fn(),
  getTaskWorkbench: vi.fn(),
}));

function project(actor: string, scopes: string[]): ProjectWorkbench {
  return {
    ...labelingProject,
    project: { ...labelingProject.project, workflow_tier: "group" },
    effective_scopes: { actor, scopes, zero_users: false },
    next_cursor: "next-page",
  };
}

function index(data: ProjectWorkbench): WorkbenchIndex {
  return {
    ...labelingIndex,
    actor: data.effective_scopes.actor,
    zero_users: false,
    effective_scopes: data.effective_scopes,
    projects: [data.project],
  };
}

function task(id = "task-1"): TaskWorkbench {
  return {
    ...labelingTask,
    task: { ...labelingTask.task, id },
    sample: {
      ...labelingTask.sample,
      media_type: "text/plain",
      content_url: "",
      text: "Generated scoped text",
    },
  };
}

beforeEach(() => {
  sessionStorage.clear();
  vi.mocked(getWorkbench).mockReset();
  vi.mocked(getProjectWorkbench).mockReset();
  vi.mocked(getTaskWorkbench)
    .mockReset()
    .mockImplementation((id) => Promise.resolve(task(id)));
});
afterEach(() => {
  vi.useRealTimers();
  sessionStorage.clear();
});

it("revalidates a changed actor after a fresh boot and rejects the previous actor's late snapshots", async () => {
  const first = project("actor-a", ["production:annotate"]);
  const second = project("actor-b", ["production:review"]);
  let current = first;
  vi.mocked(getWorkbench).mockImplementation(() =>
    Promise.resolve(index(current)),
  );
  vi.mocked(getProjectWorkbench).mockImplementation(() =>
    Promise.resolve(current),
  );
  expect(readWorkspaceSnapshot()).toBeNull();
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  await waitFor(() => {
    expect(result.current.project?.effective_scopes.actor).toBe("actor-a");
    expect(result.current.verified).toBe(true);
  });
  await act(async () => {
    await result.current.selectPackage("private-package");
  });
  await act(async () => {
    await result.current.paginate(1);
  });
  await waitFor(() => {
    expect(result.current.page).toBe(1);
  });
  result.current.cache.set("task-1", task());
  await act(async () => {
    await result.current.open("task-1");
  });
  expect(result.current.task?.task.id).toBe("task-1");
  const oldReceiveTask = result.current.receiveTask;
  current = second;
  act(() => {
    window.dispatchEvent(new Event("online"));
  });
  await waitFor(() => {
    expect(result.current.index?.actor).toBe("actor-b");
    expect(result.current.project?.effective_scopes.actor).toBe("actor-b");
  });
  expect(result.current.task).toBeNull();
  expect(result.current.cache.peek("task-1")).toBeNull();
  expect(result.current.packageId).toBe("");
  expect(result.current.page).toBe(0);
  expect(result.current.view).toBe("reviews");
  expect(result.current.project?.effective_scopes.scopes).toEqual([
    "production:review",
  ]);
  expect(getProjectWorkbench).toHaveBeenLastCalledWith(
    "project",
    expect.objectContaining({ cursor: "", packageId: "", view: "review" }),
  );
  act(() => {
    oldReceiveTask(task());
  });
  expect(result.current.task).toBeNull();
  expect(result.current.cache.peek("task-1")).toBeNull();
  expect(readWorkspaceSnapshot("actor-a")).toBeNull();
  expect(readWorkspaceSnapshot("actor-b")?.task).toBeNull();
});

it("removes a previously verified project's task and scoped controls when the next read returns 403", async () => {
  const initial = project("actor-a", [
    "production:annotate",
    "production:review",
    "production:finalize",
  ]);
  vi.mocked(getWorkbench).mockResolvedValue(index(initial));
  vi.mocked(getProjectWorkbench).mockResolvedValue(initial);
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams("project=project")),
  );
  await waitFor(() => {
    expect(result.current.project?.effective_scopes.actor).toBe("actor-a");
    expect(result.current.verified).toBe(true);
  });
  result.current.cache.set("task-1", task());
  await act(async () => {
    await result.current.open("task-1");
  });
  expect(result.current.task?.task.id).toBe("task-1");
  expect(result.current.project?.effective_scopes.scopes).toContain(
    "production:finalize",
  );
  vi.mocked(getProjectWorkbench).mockRejectedValueOnce(
    new ApiError(403, "Project access revoked"),
  );
  act(() => {
    result.current.changed();
  });
  await waitFor(() => {
    expect(result.current.error).toContain("Project access revoked");
  });
  expect(result.current.project).toBeNull();
  expect(result.current.task).toBeNull();
  expect(result.current.cache.peek("task-1")).toBeNull();
  expect(readWorkspaceSnapshot("actor-a")?.project).toBeNull();
  expect(readWorkspaceSnapshot("actor-a")?.task).toBeNull();
});

it("retries transient identity verification without enabling writes early", async () => {
  vi.useFakeTimers();
  const initial = project("actor-a", ["production:annotate"]);
  vi.mocked(getWorkbench)
    .mockRejectedValueOnce(new ApiError(503, "Restarting"))
    .mockResolvedValueOnce(index(initial));
  vi.mocked(getProjectWorkbench).mockResolvedValue(initial);
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams()),
  );
  await act(async () => {
    await Promise.resolve();
  });
  expect(result.current.verified).toBe(false);
  expect(result.current.isIdentityVerified()).toBe(false);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(999);
  });
  expect(getWorkbench).toHaveBeenCalledTimes(1);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1);
  });
  expect(getWorkbench).toHaveBeenCalledTimes(2);
  expect(result.current.verified).toBe(true);
  expect(result.current.isIdentityVerified()).toBe(true);
});

it("does not blindly retry a denied identity", async () => {
  vi.useFakeTimers();
  vi.mocked(getWorkbench).mockRejectedValue(new ApiError(403, "Revoked"));
  const { result } = renderHook(() =>
    useLabelingWorkspace(new URLSearchParams()),
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10000);
  });
  expect(getWorkbench).toHaveBeenCalledTimes(1);
  expect(result.current.verified).toBe(false);
  expect(result.current.isIdentityVerified()).toBe(false);
});
